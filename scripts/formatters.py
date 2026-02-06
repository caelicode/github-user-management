#!/usr/bin/env python3

from datetime import datetime
from typing import Optional

from models import (
    ActionType,
    OrgState,
    SecurityFinding,
    SyncPlan,
    SyncResult,
)


def format_plan_markdown(plan: SyncPlan) -> str:
    lines = []
    lines.append("## Organization Sync Plan")
    lines.append("")

    if plan.validation_errors:
        lines.append("### Validation Errors")
        lines.append("")
        for err in plan.validation_errors:
            lines.append(f"- {err}")
        lines.append("")
        return "\n".join(lines)

    if not plan.has_changes:
        lines.append("**No changes detected** — organization is in sync with config.")
        lines.append("")
        lines.append(f"> Plan generated at {plan.timestamp}")
        return "\n".join(lines)

    lines.append(f"**{plan.summary}**")
    lines.append("")

    categories = {
        "Members": [ActionType.MEMBER_INVITE, ActionType.MEMBER_REMOVE, ActionType.MEMBER_UPDATE_ROLE],
        "Teams": [ActionType.TEAM_CREATE, ActionType.TEAM_UPDATE, ActionType.TEAM_DELETE],
        "Team Membership": [ActionType.TEAM_MEMBER_ADD, ActionType.TEAM_MEMBER_REMOVE, ActionType.TEAM_MEMBER_UPDATE_ROLE],
        "Team Permissions": [ActionType.TEAM_REPO_ADD, ActionType.TEAM_REPO_REMOVE, ActionType.TEAM_REPO_UPDATE],
        "Branch Protection": [ActionType.BRANCH_PROTECTION_SET, ActionType.BRANCH_PROTECTION_DELETE],
        "Repository Settings": [ActionType.REPO_UPDATE],
    }

    for category, action_types in categories.items():
        actions = [a for a in plan.sorted_actions if a.action_type in action_types]
        if not actions:
            continue

        lines.append(f"### {category}")
        lines.append("")
        lines.append("```diff")
        for action in actions:
            prefix = {"+" : "+", "-": "-", "~": "!"}.get(action.symbol, " ")
            lines.append(f"{prefix} {action.description}")
        lines.append("```")
        lines.append("")

    if plan.warnings:
        lines.append("### Warnings")
        lines.append("")
        for warning in plan.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("---")
    lines.append(
        f"> Plan generated at {plan.timestamp} | "
        f"{plan.estimated_api_calls} API calls estimated"
    )

    return "\n".join(lines)


def format_plan_terminal(plan: SyncPlan) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("  Organization Sync Plan")
    lines.append("=" * 60)
    lines.append("")

    if plan.validation_errors:
        lines.append("VALIDATION ERRORS:")
        for err in plan.validation_errors:
            lines.append(f"  ! {err}")
        return "\n".join(lines)

    if not plan.has_changes:
        lines.append("  No changes — organization is in sync.")
        return "\n".join(lines)

    lines.append(f"  {plan.summary}")
    lines.append("")

    for action in plan.sorted_actions:
        lines.append(f"  {action.symbol} {action.description}")

    if plan.warnings:
        lines.append("")
        lines.append("  WARNINGS:")
        for w in plan.warnings:
            lines.append(f"    - {w}")

    lines.append("")
    lines.append(f"  Estimated API calls: {plan.estimated_api_calls}")
    lines.append("=" * 60)

    return "\n".join(lines)


def format_result_terminal(result: SyncResult) -> str:
    lines = []
    mode = "DRY RUN" if result.dry_run else "LIVE"
    lines.append(f"=== Sync Result ({mode}) ===")
    lines.append(f"Success: {result.success_count}")
    lines.append(f"Failed:  {result.failure_count}")
    lines.append(f"Skipped: {result.skipped_count}")

    failed_actions = [
        a for a in result.plan.actions if a.status.value == "failed"
    ]
    if failed_actions:
        lines.append("")
        lines.append("Failed actions:")
        for a in failed_actions:
            lines.append(f"  ! {a.description}: {a.error}")

    return "\n".join(lines)


def format_mermaid_diagram(state: OrgState) -> str:
    lines = []
    lines.append("```mermaid")
    lines.append("graph TD")

    org_id = "ORG"
    lines.append(f'    {org_id}["{state.org_name}"]')

    for i, team in enumerate(state.teams):
        team_id = f"T{i}"
        lines.append(f'    {org_id} --> {team_id}["{team.name}"]')

        for j, (repo_name, perm) in enumerate(team.repos.items()):
            repo_id = _repo_id(repo_name, state)
            lines.append(f'    {team_id} -->|{perm.value}| {repo_id}["{repo_name}"]')

        for member in team.members:
            member_id = _member_id(member.username)
            lines.append(
                f'    {team_id} -.->|{member.role.value}| {member_id}["{member.username}"]'
            )

    lines.append("```")
    return "\n".join(lines)


def _repo_id(name: str, state: OrgState) -> str:
    repos = [r.name for r in state.repositories]
    try:
        idx = repos.index(name)
    except ValueError:
        idx = hash(name) % 1000
    return f"R{idx}"


def _member_id(username: str) -> str:
    return f"U_{username.replace('-', '_')}"


def format_dashboard(state: OrgState, findings: list[SecurityFinding] = None) -> str:
    lines = []
    lines.append("## Organization Dashboard")
    lines.append("")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"*Last synced: {now}*")
    lines.append("")

    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Members | {len(state.members)} |")
    lines.append(f"| Teams | {len(state.teams)} |")
    lines.append(f"| Repositories | {len(state.repositories)} |")
    admin_count = sum(1 for m in state.members if m.role.value == "admin")
    lines.append(f"| Admins | {admin_count} |")
    lines.append("")

    if state.teams:
        lines.append("### Teams")
        lines.append("")
        lines.append("| Team | Members | Repos | Privacy |")
        lines.append("|------|---------|-------|---------|")
        for team in state.teams:
            lines.append(
                f"| {team.name} | {len(team.members)} | "
                f"{len(team.repos)} | {team.privacy.value} |"
            )
        lines.append("")

    if findings:
        high = [f for f in findings if f.severity == "high"]
        if high:
            lines.append("### Security Alerts")
            lines.append("")
            for f in high:
                lines.append(f"- **{f.resource}**: {f.message}")
            lines.append("")

    lines.append("### Structure")
    lines.append("")
    lines.append(format_mermaid_diagram(state))

    return "\n".join(lines)


def format_drift_report(plan: SyncPlan, findings: list[SecurityFinding] = None) -> str:
    lines = []
    lines.append("## Drift Detection Report")
    lines.append("")
    lines.append(f"*Detected at: {plan.timestamp}*")
    lines.append("")

    if not plan.has_changes:
        lines.append("No drift detected — organization matches configuration.")
        return "\n".join(lines)

    lines.append(f"**Drift detected: {plan.summary}**")
    lines.append("")
    lines.append(
        "The following differences were found between the configuration "
        "files and the actual GitHub organization state:"
    )
    lines.append("")

    for action in plan.sorted_actions:
        lines.append(f"- {action.symbol} {action.description}")

    if plan.warnings:
        lines.append("")
        lines.append("### Warnings")
        lines.append("")
        for w in plan.warnings:
            lines.append(f"- {w}")

    if findings:
        lines.append("")
        lines.append("### Security Findings")
        lines.append("")
        for f in findings:
            icon = {"high": "!!!", "medium": "!!", "low": "!"}.get(f.severity, "")
            lines.append(f"- [{f.severity.upper()}] {f.resource}: {f.message}")

    lines.append("")
    lines.append(
        "To resolve this drift, either update the config files to match "
        "the current state, or run the sync workflow to enforce the config."
    )

    return "\n".join(lines)


def format_step_summary(result: SyncResult) -> str:
    lines = []
    mode = "Dry Run" if result.dry_run else "Live"
    status = "Success" if result.success else "Failed"

    lines.append(f"## Org Sync — {status} ({mode})")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Succeeded | {result.success_count} |")
    lines.append(f"| Failed | {result.failure_count} |")
    lines.append(f"| Skipped | {result.skipped_count} |")
    lines.append("")

    if result.failure_count > 0:
        lines.append("### Failures")
        lines.append("")
        for a in result.plan.actions:
            if a.status.value == "failed":
                lines.append(f"- {a.description}: {a.error}")
        lines.append("")

    return "\n".join(lines)
