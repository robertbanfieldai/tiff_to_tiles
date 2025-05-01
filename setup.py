from setuptools import setup, find_packages

setup(
    name="tiff_to_tiles",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "rasterio",
        "numpy",
        "pyproj"
    ],
    entry_points={
        "console_scripts": [
            "tiff-to-tiles=tiff_to_tiles.cli:main"
        ]
    },
    author="Your Name",
    description="GDAL-based utility to convert GeoTIFFs to Web Mercator tiles",
)
