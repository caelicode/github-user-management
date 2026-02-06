#!/usr/bin/env python3

import argparse
import json
import logging
import os
import sys

from audit_logger import AuditLogger
from config_loader import load_config
from formatters import (
    format_plan_terminal,
    format_result_terminal,
    format_step_summary,
)
from github_client import GitHubClient
from reconciler import Reconciler
from utils import setup_logging, write_results_file
from workflow_utils import set_github_output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync the GitHub organization to match config files"
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help="Path to config directory (default: ./config/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no actual changes)",
    )

    args = parser.parse_args()

    setup_logging("apply")

    logging.info("Loading configuration...")
    desired_state, errors, warnings = load_config(
        config_dir=args.config_dir, validate=True
    )

    if errors:
        logging.error("Validation errors — aborting:")
        for err in errors:
            logging.error(f"  - {err}")
        return 1

    for w in warnings:
        logging.warning(f"  - {w}")

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logging.error("GITHUB_TOKEN environment variable not set")
        return 1

    client = GitHubClient(token)
    reconciler = Reconciler(client, desired_state.org_name)

    logging.info("Fetching current state from GitHub...")
    current_state = reconciler.fetch_current_state()

    logging.info("Generating sync plan...")
    plan = reconciler.diff(desired_state, current_state)
    plan.warnings.extend(warnings)

    print(format_plan_terminal(plan))

    if not plan.has_changes:
        logging.info("Organization is already in sync — nothing to do.")
        set_github_output("sync_status", "no_changes")
        return 0

    dry_run = args.dry_run or os.environ.get("DRY_RUN", "false").lower() == "true"
    mode = "DRY RUN" if dry_run else "LIVE"
    logging.info(f"Executing plan ({mode})...")

    result = reconciler.apply(plan, dry_run=dry_run)

    audit = AuditLogger(prefix="sync_audit")
    audit.log_result(result)
    logging.info(audit.get_summary())

    write_results_file("sync_results.json", result.to_dict())

    print(format_result_terminal(result))

    set_github_output("sync_status", "success" if result.success else "failed")
    set_github_output("success_count", str(result.success_count))
    set_github_output("failure_count", str(result.failure_count))

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a") as f:
            f.write(format_step_summary(result) + "\n")

    if result.success:
        logging.info("Sync completed successfully.")
        return 0
    else:
        logging.error(f"Sync completed with {result.failure_count} failure(s).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
