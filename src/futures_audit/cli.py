from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run_pipeline, validate_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run auditable futures strategy replications")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Fetch official data and run all published strategies")
    run_parser.add_argument("--config", default="configs/base.toml")
    subparsers.add_parser("validate", help="Validate generated outputs and report freshness")
    args = parser.parse_args()
    root = Path.cwd()
    if args.command == "run":
        result = run_pipeline(root, root / args.config)
        print(f"Completed local pipeline through {result['manifest']['coverage']['common']['end']}")
    else:
        validate_outputs(root)
        print("Output validation passed")


if __name__ == "__main__":
    main()

