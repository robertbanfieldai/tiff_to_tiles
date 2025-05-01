import os
import uuid
import math
import subprocess
import rasterio
import numpy as np
import shutil
from pyproj import Transformer


class TileGenerator:
    """Generate XYZ tiles from an input raster, preserving an existing alpha band.

    The class performs percentile‑based (or manual) scaling of the three RGB bands
    to 8‑bit and forwards an existing alpha band so that transparency is driven
    by the alpha channel instead of a band‑level NODATA value. Pixels that fall
    outside the chosen scaling range are clamped to 0/255 (very dark / bright)
    and *remain visible* because the bands themselves carry no NODATA flag.
    """

    def __init__(
        self,
        input_file: str,
        red: int | None = None,
        green: int | None = None,
        blue: int | None = None,
        scale: tuple[float, float, float, float, float, float] | None = None,
        verbose: bool = True,
        use_minmax: bool = False,
        percentile_range: tuple[float, float] = (2.5, 97.5),
    ) -> None:
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
        self.vrt_path = os.path.join(self.output_dir, "scaled_rgba.vrt")
        self.gdal2tiles_cmd = self._check_required_tools()

    # ------------------------------------------------------------------ helpers
    def _check_required_tools(self) -> str:
        """Ensure GDAL utilities are reachable and return the gdal2tiles command."""
        required = ["gdal_translate", "gdal2tiles", "gdal2tiles.py"]
        found: list[str] = []
        for tool in required:
            if shutil.which(tool):
                found.append(tool)
        if "gdal_translate" not in found:
            raise RuntimeError("Error: 'gdal_translate' is not installed or not in PATH.")
        if "gdal2tiles" in found:
            return "gdal2tiles"
        if "gdal2tiles.py" in found:
            return "gdal2tiles.py"
        raise RuntimeError("Error: 'gdal2tiles' is not installed or not in PATH.")

    @staticmethod
    def _find_rgb_bands(src: rasterio.io.DatasetReader) -> tuple[int, int, int]:
        """Detect Red/Green/Blue band indices via color interpretation or description."""
        band_map: dict[str, int] = {}
        # first pass – colour interpretation
        for idx, ci in enumerate(src.colorinterp, start=1):
            if ci.name.lower() == "red":
                band_map["Red"] = idx
            elif ci.name.lower() == "green":
                band_map["Green"] = idx
            elif ci.name.lower() == "blue":
                band_map["Blue"] = idx
        # second pass – exact description match
        for idx, desc in enumerate(src.descriptions, start=1):
            if desc:
                d = desc.lower()
                if d == "red" and "Red" not in band_map:
                    band_map["Red"] = idx
                elif d == "green" and "Green" not in band_map:
                    band_map["Green"] = idx
                elif d == "blue" and "Blue" not in band_map:
                    band_map["Blue"] = idx
        # third pass – fuzzy description contains("red"/"green"/"blue")
        for idx, desc in enumerate(src.descriptions, start=1):
            if desc:
                d = desc.lower()
                if "red" in d and "Red" not in band_map:
                    band_map["Red"] = idx
                elif "green" in d and "Green" not in band_map:
                    band_map["Green"] = idx
                elif "blue" in d and "Blue" not in band_map:
                    band_map["Blue"] = idx
        if len(band_map) < 3:
            raise RuntimeError(f"Could not detect RGB bands. Found: {band_map}")
        return band_map["Red"], band_map["Green"], band_map["Blue"]

    @staticmethod
    def _find_alpha_band(src: rasterio.io.DatasetReader) -> int | None:
        for idx, ci in enumerate(src.colorinterp, start=1):
            if ci.name.lower() == "alpha":
                return idx
        return None

    def _compute_percentiles(
        self, data: np.ndarray, nodata: float | int | None
    ) -> tuple[float, float, float, float]:
        """Return p_low, p_high, min_val, max_val for a data block."""
        if nodata is None:
            valid = data
        else:
            valid = data[data != nodata]
        min_val = float(valid.min())
        max_val = float(valid.max())
        if self.use_minmax:
            return min_val, max_val, min_val, max_val
        p_low = float(np.percentile(valid, self.percentile_range[0]))
        p_high = float(np.percentile(valid, self.percentile_range[1]))
        return p_low, p_high, min_val, max_val

    @staticmethod
    def _compute_max_zoom(native_res_mpp: float, latitude_deg: float) -> int:
        lat = min(abs(latitude_deg), 85.0511)
        for z in range(30):
            res_merc = (156543.03392 * math.cos(math.radians(lat))) / (2**z)
            if res_merc <= native_res_mpp:
                return z
        return 30

    # ------------------------------------------------------------------- main run
    def run(self) -> None:
        """Create scaled RGB(A) VRT and build XYZ tiles under *output_dir*."""
        with rasterio.open(self.input_file) as src:
            nodata = src.nodata  # may be None – we now ignore it in output
            if self.red and self.green and self.blue:
                bands = [(self.red, "Red"), (self.green, "Green"), (self.blue, "Blue")]
            else:
                r, g, b = self._find_rgb_bands(src)
                bands = [(r, "Red"), (g, "Green"), (b, "Blue")]

            # build per‑band scaling
            if self.scale:
                if self.verbose:
                    print("Using manually provided scale values:")
                    print(f"  Red:   {self.scale[0]}–{self.scale[1]}")
                    print(f"  Green: {self.scale[2]}–{self.scale[3]}")
                    print(f"  Blue:  {self.scale[4]}–{self.scale[5]}")
                scales = [
                    (self.scale[0], self.scale[1]),
                    (self.scale[2], self.scale[3]),
                    (self.scale[4], self.scale[5]),
                ]
            else:
                scales: list[tuple[float, float]] = []
                for band_num, _ in bands:
                    data = src.read(band_num)
                    p_min, p_max, min_val, max_val = self._compute_percentiles(data, nodata)
                    scales.append((p_min, p_max))
                    if self.verbose:
                        if self.use_minmax:
                            print(
                                f"Band {band_num}: using full min/max range: {min_val:.4f} to {max_val:.4f}"
                            )
                        else:
                            pl, ph = self.percentile_range
                            print(
                                f"Band {band_num}: min = {min_val:.4f}, max = {max_val:.4f}, {pl}th = {p_min:.4f}, {ph}th = {p_max:.4f}"
                            )

            # compute appropriate max zoom to avoid oversampling
            transform = src.transform
            native_res_mpp = max(abs(transform[0]), abs(transform[4]))
            bounds = src.bounds
            transformer = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
            _, lat_top = transformer.transform((bounds.left + bounds.right) / 2, bounds.top)
            _, lat_bottom = transformer.transform((bounds.left + bounds.right) / 2, bounds.bottom)
            effective_lat = max(abs(lat_top), abs(lat_bottom), 0)
            max_zoom = self._compute_max_zoom(native_res_mpp, effective_lat)
            if self.verbose:
                print("Determined max zoom level to avoid oversampling:")
                print(f"  Native resolution: {native_res_mpp:.6f} meters/pixel")
                print(f"  Effective latitude: {effective_lat:.6f} degrees")
                print(f"  Using maximum zoom level: {max_zoom}")

            # look for an existing alpha band
            alpha_band = self._find_alpha_band(src)
            if alpha_band is None:
                raise RuntimeError("Input raster does not contain an alpha band to forward.")

        # ---------------------------------------------------------------- translate
        cmd_translate: list[str] = [
            "gdal_translate",
            "-ot",
            "Byte",
            "-of",
            "VRT",
            "-a_nodata",
            "none",  # remove NODATA so clamped pixels stay visible
        ]

        # scaling arguments
        for i, (p_min, p_max) in enumerate(scales, start=1):
            cmd_translate += [f"-scale_{i}", str(p_min), str(p_max), "0", "255"]

        # band selection – RGB followed by Alpha
        for band_num, _ in bands:
            cmd_translate += ["-b", str(band_num)]
        cmd_translate += ["-b", str(alpha_band)]

        # input and output
        cmd_translate += [self.input_file, self.vrt_path]

        if self.verbose:
            print("Creating scaled RGBA VRT (alpha preserved)...")
        subprocess.run(cmd_translate, check=True)

        # -------------------------------------------------------------- gdal2tiles
        cmd_tiles = [self.gdal2tiles_cmd, "-z", f"0-{max_zoom}", self.vrt_path, self.output_dir]
        if self.verbose:
            print("Running gdal2tiles – generating XYZ tiles…")
        subprocess.run(cmd_tiles, check=True)

        # cleanup + info
        os.remove(self.vrt_path)
        if self.verbose:
            print(f"Done. All output saved in: {self.output_dir}")
