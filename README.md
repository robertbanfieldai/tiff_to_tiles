# tiff_to_tiles

`tiff_to_tiles` is a Python command-line tool and library for converting GeoTIFF imagery into Web Mercator tiles using `gdal2tiles`. It automatically detects RGB bands, scales float data to byte, and selects the maximum zoom level that does not oversample the raster resolution based on geographic latitude.

## Features

- Automatically detects red, green, and blue bands (with manual override)
- Scales each band to 0–255 using the 2.5th and 97.5th percentiles by default (manual override supported)
- Computes maximum safe zoom level using geographic location to avoid oversampling
- Outputs a folder of tiles compatible with web mapping
- Verbose output enabled by default for transparency

## Installation (Fedora)

Install system dependencies:

```bash
sudo dnf install python python-pip gdal gdal-python-tools
```

Then clone and install the package:

```bash
git clone https://github.com/robertbanfieldai/tiff_to_tiles.git
cd tiff_to_tiles
pip install -e .
```

This installs the `tiff-to-tiles` command for use on your system.

## Usage

```bash
tiff-to-tiles input.tif
```

### Optional arguments:

- `--red`, `--green`, `--blue` — manually specify the band numbers for RGB
- `--scale RMIN RMAX GMIN GMAX BMIN BMAX` — manually specify per-channel scaling
- `--verbose false` — disable verbose output

Example with overrides:

```bash
tiff-to-tiles input.tif --red 4 --green 2 --blue 1 --scale 0 10000 0 10000 0 10000 --verbose false
```
