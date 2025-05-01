import os
import uuid
import math
import subprocess
import rasterio
import numpy as np
import shutil
from pyproj import Transformer

class TileGenerator:
    def __init__(self, input_file, red=None, green=None, blue=None, scale=None, verbose=True, use_minmax=False, percentile_range=(2.5, 97.5)):
        self.input_file = input_file
        self.red = red
        self.green = green
        self.blue = blue
        self.scale = scale
        self.verbose = verbose
        self.use_minmax = use_minmax
        self.percentile_range = percentile_range
        self.output_dir = f"tiles_output_{uuid.uuid4().hex[:8]}"
        os.makedirs(self.output_dir, exist_ok=True)
        self.vrt_path = os.path.join(self.output_dir, "scaled_rgb.vrt")
        self.gdal2tiles_cmd = self.check_required_tools()

    def check_required_tools(self):
        required = ["gdal_translate", "gdal2tiles", "gdal2tiles.py"]
        found = []
        for tool in required:
            path = shutil.which(tool)
            if path:
                found.append(tool)
        if "gdal_translate" not in found:
            raise RuntimeError("Error: 'gdal_translate' is not installed or not in PATH.")
        if "gdal2tiles" in found:
            return "gdal2tiles"
        elif "gdal2tiles.py" in found:
            return "gdal2tiles.py"
        else:
            raise RuntimeError("Error: 'gdal2tiles' or 'gdal2tiles.py' is not installed or not in PATH.")

    def find_rgb_bands(self, src):
        colorinterp = src.colorinterp
        descriptions = src.descriptions
        band_map = {}
        for idx, ci in enumerate(colorinterp, start=1):
            if ci.name.lower() == 'red':
                band_map['Red'] = idx
            elif ci.name.lower() == 'green':
                band_map['Green'] = idx
            elif ci.name.lower() == 'blue':
                band_map['Blue'] = idx
        for idx, desc in enumerate(descriptions, start=1):
            if not desc:
                continue
            d = desc.lower()
            if d == 'red' and 'Red' not in band_map:
                band_map['Red'] = idx
            elif d == 'green' and 'Green' not in band_map:
                band_map['Green'] = idx
            elif d == 'blue' and 'Blue' not in band_map:
                band_map['Blue'] = idx
        for idx, desc in enumerate(descriptions, start=1):
            if not desc:
                continue
            d = desc.lower()
            if 'red' in d and 'Red' not in band_map:
                band_map['Red'] = idx
            elif 'green' in d and 'Green' not in band_map:
                band_map['Green'] = idx
            elif 'blue' in d and 'Blue' not in band_map:
                band_map['Blue'] = idx
        if len(band_map) < 3:
            raise RuntimeError(f"Could not detect RGB bands. Found: {band_map}")
        return band_map['Red'], band_map['Green'], band_map['Blue']

    def compute_percentiles(self, data, nodata):
        valid = data[data != nodata]
        min_val = valid.min()
        max_val = valid.max()

        if self.use_minmax:
            return min_val, max_val, min_val, max_val

        p_low = np.percentile(valid, self.percentile_range[0])
        p_high = np.percentile(valid, self.percentile_range[1])
        return p_low, p_high, min_val, max_val

    def compute_max_zoom(self, native_res_mpp, latitude_deg):
        latitude_deg = min(abs(latitude_deg), 85.0511)
        for z in range(30):
            res_merc = (156543.03392 * math.cos(math.radians(latitude_deg))) / (2 ** z)
            if res_merc <= native_res_mpp:
                return z
        return 30

    def run(self):
        with rasterio.open(self.input_file) as src:
            nodata = src.nodata or -10000

            if self.red and self.green and self.blue:
                bands = [(self.red, "Red"), (self.green, "Green"), (self.blue, "Blue")]
            else:
                r_band, g_band, b_band = self.find_rgb_bands(src)
                bands = [(r_band, "Red"), (g_band, "Green"), (b_band, "Blue")]

            if self.scale:
                if self.verbose:
                    print("Using manually provided scale values:")
                    print(f"  Red:   {self.scale[0]}–{self.scale[1]}")
                    print(f"  Green: {self.scale[2]}–{self.scale[3]}")
                    print(f"  Blue:  {self.scale[4]}–{self.scale[5]}")
                scales = [
                    (self.scale[0], self.scale[1]),
                    (self.scale[2], self.scale[3]),
                    (self.scale[4], self.scale[5])
                ]
            else:
                scales = []
                for band_num, _ in bands:
                    data = src.read(band_num)
                    p_min, p_max, min_val, max_val = self.compute_percentiles(data, nodata)
                    scales.append((p_min, p_max))
                    if self.verbose:
                        if self.use_minmax:
                            print(f"Band {band_num}: using full min/max range: {min_val:.4f} to {max_val:.4f}")
                        else:
                            print(f"Band {band_num}: min = {min_val:.4f}, max = {max_val:.4f}, {self.percentile_range[0]}th = {p_min:.4f}, {self.percentile_range[1]}th = {p_max:.4f}")

            transform = src.transform
            native_res_mpp = max(abs(transform[0]), abs(transform[4]))
            bounds = src.bounds
            transformer = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
            _, lat_top = transformer.transform((bounds.left + bounds.right) / 2, bounds.top)
            _, lat_bottom = transformer.transform((bounds.left + bounds.right) / 2, bounds.bottom)
            effective_lat = max(abs(lat_top), abs(lat_bottom), 0)
            max_zoom = self.compute_max_zoom(native_res_mpp, effective_lat)
            if self.verbose:
                print("Determined max zoom level to avoid oversampling:")
                print(f"  Native resolution: {native_res_mpp:.6f} meters/pixel")
                print(f"  Effective latitude: {effective_lat:.6f} degrees")
                print(f"  Using maximum zoom level: {max_zoom}")

        cmd_translate = ["gdal_translate", "-ot", "Byte", "-of", "VRT"]
        for i, (p_min, p_max) in enumerate(scales, start=1):
            cmd_translate += [f"-scale_{i}", str(p_min), str(p_max), "0", "255"]
        for band_num, _ in bands:
            cmd_translate += ["-b", str(band_num)]
        cmd_translate += [self.input_file, self.vrt_path]

        if self.verbose:
            print("Creating scaled RGB VRT...")
        subprocess.run(cmd_translate, check=True)

        cmd_tiles = [self.gdal2tiles_cmd, "-z", f"0-{max_zoom}", self.vrt_path, self.output_dir]
        if self.verbose:
            print("Running gdal2tiles...")
        subprocess.run(cmd_tiles, check=True)

        os.remove(self.vrt_path)
        if self.verbose:
            print(f"Done. All output saved in: {self.output_dir}")
