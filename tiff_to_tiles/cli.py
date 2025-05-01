import argparse
from tiff_to_tiles.tile_generator import TileGenerator

def main():
    parser = argparse.ArgumentParser(description="Convert GeoTIFF to Web Mercator tiles without oversampling.")
    parser.add_argument("input_file", help="Path to input GeoTIFF")
    parser.add_argument("--red", type=int, help="Band number to use for Red")
    parser.add_argument("--green", type=int, help="Band number to use for Green")
    parser.add_argument("--blue", type=int, help="Band number to use for Blue")
    parser.add_argument("--scale", nargs=6, metavar=("RMIN", "RMAX", "GMIN", "GMAX", "BMIN", "BMAX"),
                        type=float, help="Manual scaling for R, G, B bands")
    parser.add_argument("--verbose", type=bool, default=True, help="Enable verbose output (default: True)")
    parser.add_argument("--use-minmax", action="store_true",
                        help="Use full min/max range for scaling instead of percentiles")
    parser.add_argument("--percentile-range", nargs=2, metavar=("P_LOW", "P_HIGH"),
                        type=float, default=(2.5, 97.5),
                        help="Percentile range to use for auto-scaling (default: 2.5 97.5)")

    args = parser.parse_args()

    generator = TileGenerator(
        input_file=args.input_file,
        red=args.red,
        green=args.green,
        blue=args.blue,
        scale=args.scale,
        verbose=args.verbose,
        use_minmax=args.use_minmax,
        percentile_range=tuple(args.percentile_range)
    )

    generator.run()
