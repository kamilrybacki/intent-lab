"""CLI entrypoint for the evaluation script."""

from __future__ import annotations

import argparse

from src.evaluator.report import run_aggregate, run_all_experiments, run_single


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Hallucinating Splines cities by Intent group.",
        epilog=(
            "Single: %(prog)s CITY_A CITY_B  |  "
            "Pool: %(prog)s --meta FILE  |  "
            "All runs: %(prog)s --all-runs"
        ),
    )
    parser.add_argument("city_a", nargs="?", default=None)
    parser.add_argument("city_b", nargs="?", default=None)
    parser.add_argument(
        "--meta",
        metavar="FILE",
        default=None,
        help="Path to experiment_meta.json for pool evaluation",
    )
    parser.add_argument(
        "--all-runs",
        action="store_true",
        default=False,
        help="Query Redis for ALL historical experiments and produce a cross-run report",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Path to write raw JSON data dump",
    )
    args = parser.parse_args()

    if args.all_runs:
        run_all_experiments(args.output)
    elif args.meta:
        run_aggregate(args.meta, args.output)
    elif args.city_a and args.city_b:
        run_single(args.city_a, args.city_b, args.output)
    else:
        parser.error("Provide --all-runs, --meta FILE, or two city IDs.")
