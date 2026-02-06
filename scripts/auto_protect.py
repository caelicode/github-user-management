#!/usr/bin/env python3

import argparse
import json
import logging
import os
import sys

from github_client import GitHubClient
from config_loader import load_config
from utils import load_yaml_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DEFAULT_PROTECTION = {
    "required_pull_request_reviews": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews": True,
    },
    "enforce_admins": False,
    "required_status_checks": None,
    "restrictions": None,
}


def get_client():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("ORG_MANAGER_TOKEN")
    if not token:
        log.error("GITHUB_TOKEN or ORG_MANAGER_TOKEN environment variable required")
        sys.exit(1)
    return GitHubClient(token)


def get_org_name(config_dir: str) -> str:
    env_org = os.environ.get("ORG_NAME")
    if env_org:
        return env_org
    try:
        org_data = load_yaml_file(os.path.join(config_dir, "org.yml"))
        return org_data.get("org_name", org_data.get("name", ""))
    except Exception:
        log.error("Cannot determine org name from config or ORG_NAME env var")
        sys.exit(1)


def load_managed_repos(config_dir: str) -> dict:
    try:
        state, errors, warnings = load_config(config_dir, validate=False)
        return {
            r.name: len(r.branch_protection) > 0
            for r in state.repositories
        }
    except Exception as e:
        log.warning(f"Could not load config: {e}. Treating all repos as unmanaged.")
        return {}


def main():
    parser = argparse.ArgumentParser(
        description="Auto-detect new repos and apply default branch protection"
    )
    parser.add_argument(
        "--config-dir", default="config",
        help="Config directory (default: config)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would happen without making changes"
    )
    parser.add_argument(
        "--exclude", nargs="*", default=[],
        help="Repo names to exclude from auto-protection"
    )
    args = parser.parse_args()

    client = get_client()
    org = get_org_name(args.config_dir)
    if not org:
        log.error("Org name is empty")
        sys.exit(1)

    log.info(f"Auto-protect scan for org: {org}")

    managed = load_managed_repos(args.config_dir)
    excluded = set(args.exclude)

    for name, has_protection in managed.items():
        if not has_protection:
            excluded.add(name)
            log.info(f"  Skipping '{name}' — managed in config with no branch protection (intentional)")

    all_repos = client.list_org_repos(org)
    if not all_repos:
        log.warning("No repos found (or API error)")
        write_summary("## Auto-Protect\n\nNo repositories found in org.\n")
        return

    log.info(f"Found {len(all_repos)} total repo(s) in {org}")

    newly_protected = []
    already_protected = []
    skipped_private = []
    skipped_excluded = []
    skipped_managed = []
    failed = []

    for repo in all_repos:
        name = repo["name"]
        is_private = repo.get("private", True)
        default_branch = repo.get("default_branch", "main")

        if name in excluded:
            skipped_excluded.append(name)
            continue

        if name in managed and managed[name]:
            skipped_managed.append(name)
            continue

        if is_private:
            skipped_private.append(name)
            continue

        existing = client.get_branch_protection(org, name, default_branch)
        if existing:
            already_protected.append(name)
            log.info(f"  '{name}' already has branch protection — skipping")
            continue

        log.info(f"  '{name}' (public, unprotected) → applying default protection")

        if args.dry_run:
            log.info(f"    [DRY RUN] Would protect {name}/{default_branch}")
            newly_protected.append(name)
            continue

        success, msg = client.set_branch_protection(
            org, name, default_branch, DEFAULT_PROTECTION
        )
        if success:
            log.info(f"    ✓ Protected {name}/{default_branch}")
            newly_protected.append(name)
        else:
            log.error(f"    ✗ Failed to protect {name}: {msg}")
            failed.append({"name": name, "error": msg})

    prefix = "[DRY RUN] " if args.dry_run else ""
    summary_lines = [f"## {prefix}Auto-Protect Summary\n"]

    if newly_protected:
        summary_lines.append(f"### {'Would protect' if args.dry_run else 'Newly protected'} ({len(newly_protected)})")
        for name in newly_protected:
            summary_lines.append(f"- `{name}` → default branch protection (1 required review, dismiss stale)")
        summary_lines.append("")

    if failed:
        summary_lines.append(f"### Failed ({len(failed)})")
        for f in failed:
            summary_lines.append(f"- `{f['name']}`: {f['error']}")
        summary_lines.append("")

    if skipped_private:
        summary_lines.append(f"### Skipped — private ({len(skipped_private)})")
        summary_lines.append("Branch protection requires GitHub Team/Enterprise for private repos.")
        for name in skipped_private:
            summary_lines.append(f"- `{name}`")
        summary_lines.append("")

    if skipped_excluded:
        summary_lines.append(f"### Skipped — excluded ({len(skipped_excluded)})")
        for name in skipped_excluded:
            summary_lines.append(f"- `{name}`")
        summary_lines.append("")

    if skipped_managed:
        summary_lines.append(f"### Skipped — already managed in config ({len(skipped_managed)})")
        for name in skipped_managed:
            summary_lines.append(f"- `{name}`")
        summary_lines.append("")

    if already_protected:
        summary_lines.append(f"### Skipped — already protected ({len(already_protected)})")
        for name in already_protected:
            summary_lines.append(f"- `{name}`")
        summary_lines.append("")

    if not newly_protected and not failed:
        summary_lines.append("All public repos are protected. Nothing to do.\n")

    unmanaged_repos = [
        r["name"] for r in all_repos
        if r["name"] not in managed
    ]
    if unmanaged_repos:
        summary_lines.append("### Unmanaged repos (not in config/repositories.yml)")
        summary_lines.append(
            "These repos are not tracked in your GitOps config. "
            "Add them to `config/repositories.yml` for full management."
        )
        for name in unmanaged_repos:
            summary_lines.append(f"- `{name}`")
        summary_lines.append("")

    summary = "\n".join(summary_lines)
    write_summary(summary)

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as f:
            f.write(f"protected_count={len(newly_protected)}\n")
            f.write(f"failed_count={len(failed)}\n")
            unmanaged_csv = ",".join(unmanaged_repos) if unmanaged_repos else ""
            f.write(f"unmanaged_repos={unmanaged_csv}\n")

    if failed:
        sys.exit(1)
    elif newly_protected:
        sys.exit(2)
    else:
        sys.exit(0)


def write_summary(text: str):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(text)
    print(text)


if __name__ == "__main__":
    main()
