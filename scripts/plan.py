#!/usr/bin/env python3

import argparse
import json
import logging
import os
import sys

from config_loader import load_config
from formatters import (
    format_drift_report,
    format_plan_markdown,
    format_plan_terminal,
)
from github_client import GitHubClient
from models import SyncPlan
from reconciler import Reconciler
from utils import setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a sync plan for the GitHub organization"
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help="Path to config directory (default: ./config/)",
    )
    parser.add_argument(
        "--format",
        choices=["terminal", "markdown", "json", "drift"],
        default="terminal",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write output to file instead of stdout",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate config files, don't query GitHub",
    )

    args = parser.parse_args()

    setup_logging("plan")

    logging.info("Loading configuration...")
    desired_state, errors, warnings = load_config(
        config_dir=args.config_dir, validate=True
    )

    if errors:
        logging.error("Validation errors found:")
        for err in errors:
            logging.error(f"  - {err}")

        plan = SyncPlan(
            org_name=desired_state.org_name or "unknown",
            validation_errors=errors,
            warnings=warnings,
        )
        _output(plan, args)
        return 1

    for w in warnings:
        logging.warning(f"  - {w}")

    if args.validate_only:
        logging.info("Config validation passed.")
        if warnings:
            logging.info(f"  {len(warnings)} warning(s)")
        return 0

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logging.error("GITHUB_TOKEN environment variable not set")
        return 1

    client = GitHubClient(token)
    reconciler = Reconciler(client, desired_state.org_name)

    logging.info("Fetching current state from GitHub...")
    current_state = reconciler.fetch_current_state()

    logging.info("Generating plan...")
    plan = reconciler.diff(desired_state, current_state)
    plan.warnings.extend(warnings)

    _output(plan, args)

    if plan.has_changes:
        return 2
    return 0


def _output(plan: SyncPlan, args) -> None:
    formatters = {
        "terminal": format_plan_terminal,
        "markdown": format_plan_markdown,
        "json": lambda p: json.dumps(p.to_dict(), indent=2),
        "drift": format_drift_report,
    }

    formatter = formatters[args.format]
    output = formatter(plan)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        logging.info(f"Plan written to {args.output}")
    else:
        print(output)

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        md_output = format_plan_markdown(plan)
        with open(summary_file, "a") as f:
            f.write(md_output + "\n")


if __name__ == "__main__":
    sys.exit(main())
