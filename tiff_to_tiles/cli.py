#!/usr/bin/env python3
import argparse
from tiff_to_tiles.tile_generator import TileGenerator

def main():
    parser = argparse.ArgumentParser(description="Generate gdal2tiles from a GeoTIFF with auto-scaling and safe zoom limits.")
    parser.add_argument("input_file", help="Path to input GeoTIFF")
    parser.add_argument("--red", type=int, help="Band number to use for Red")
    parser.add_argument("--green", type=int, help="Band number to use for Green")
    parser.add_argument("--blue", type=int, help="Band number to use for Blue")
    parser.add_argument("--scale", nargs=6, metavar=("RMIN", "RMAX", "GMIN", "GMAX", "BMIN", "BMAX"),
                        type=float, help="Manual scaling for R, G, B bands")
    args = parser.parse_args()

    generator = TileGenerator(
        input_file=args.input_file,
        red=args.red,
        green=args.green,
        blue=args.blue,
        scale=args.scale
    )
    generator.run()

if __name__ == "__main__":
    main()
