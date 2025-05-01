import os
import uuid
import math
import subprocess
import rasterio
import numpy as np
import shutil
from pyproj import Transformer

class TileGenerator:
    def __init__(self, input_file, red=None, green=None, blue=None, scale=None):
        self.input_file = input_file
        self.red = red
        self.green = green
        self.blue = blue
        self.scale = scale
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
        return np.percentile(valid, 2.5), np.percentile(valid, 97.5)

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
                scales = [
                    (self.scale[0], self.scale[1]),
                    (self.scale[2], self.scale[3]),
                    (self.scale[4], self.scale[5])
                ]
            else:
                scales = []
                for band_num, _ in bands:
                    data = src.read(band_num)
                    p2, p98 = self.compute_percentiles(data, nodata)
                    scales.append((p2, p98))

            transform = src.transform
            native_res_mpp = max(abs(transform[0]), abs(transform[4]))
            bounds = src.bounds
            transformer = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
            _, lat_top = transformer.transform((bounds.left + bounds.right) / 2, bounds.top)
            _, lat_bottom = transformer.transform((bounds.left + bounds.right) / 2, bounds.bottom)
            effective_lat = max(abs(lat_top), abs(lat_bottom), 0)
            max_zoom = self.compute_max_zoom(native_res_mpp, effective_lat)

        cmd_translate = ["gdal_translate", "-ot", "Byte", "-of", "VRT"]
        for i, (p2, p98) in enumerate(scales, start=1):
            cmd_translate += [f"-scale_{i}", str(p2), str(p98), "0", "255"]
        for band_num, _ in bands:
            cmd_translate += ["-b", str(band_num)]
        cmd_translate += [self.input_file, self.vrt_path]

        print("Creating scaled RGB VRT...")
        subprocess.run(cmd_translate, check=True)

        cmd_tiles = [self.gdal2tiles_cmd, "-z", f"0-{max_zoom}", self.vrt_path, self.output_dir]
        print("Running gdal2tiles...")
        subprocess.run(cmd_tiles, check=True)

        os.remove(self.vrt_path)
        print(f"Done. All output saved in: {self.output_dir}")
