#!/usr/bin/env python3
"""Configuration validation for organization management.

Validates YAML config files against JSON schemas and performs
referential integrity checks across config files.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:
    jsonschema = None

from models import RepoVisibility


SCHEMA_DIR = Path(__file__).parent.parent / "schemas"


def _load_schema(schema_name: str) -> dict:
    """Load a JSON schema file from the schemas directory."""
    schema_path = SCHEMA_DIR / f"{schema_name}.schema.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    with open(schema_path, "r") as f:
        return json.load(f)


def validate_schema(data: dict, schema_name: str) -> list[str]:
    """Validate data against a JSON schema. Returns list of errors."""
    if jsonschema is None:
        logging.warning("jsonschema not installed — skipping schema validation")
        return []

    try:
        schema = _load_schema(schema_name)
    except FileNotFoundError as e:
        return [str(e)]

    errors = []
    validator = jsonschema.Draft7Validator(schema)
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = " → ".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"[{schema_name}] {path}: {error.message}")

    return errors


def validate_members_config(members_data: dict) -> list[str]:
    """Validate members.yml structure and content."""
    errors = validate_schema(members_data, "members")

    members = members_data.get("members", [])
    if not isinstance(members, list):
        return errors

    # Check for duplicate usernames
    usernames = [m.get("username", "") for m in members if isinstance(m, dict)]
    seen = set()
    for u in usernames:
        if u in seen:
            errors.append(f"[members] Duplicate username: {u}")
        seen.add(u)

    return errors


def validate_teams_config(teams_data: dict) -> list[str]:
    """Validate teams.yml structure and content."""
    errors = validate_schema(teams_data, "teams")

    teams = teams_data.get("teams", {})
    if not isinstance(teams, dict):
        return errors

    for team_name, team_config in teams.items():
        if not isinstance(team_config, dict):
            continue

        # Check for duplicate members within a team
        members = team_config.get("members", [])
        usernames = [m.get("username", "") for m in members if isinstance(m, dict)]
        seen = set()
        for u in usernames:
            if u in seen:
                errors.append(f"[teams] Duplicate member '{u}' in team '{team_name}'")
            seen.add(u)

    return errors


def validate_repositories_config(repos_data: dict) -> list[str]:
    """Validate repositories.yml structure and content."""
    return validate_schema(repos_data, "repositories")


def validate_cross_references(
    members_data: dict,
    teams_data: dict,
    repos_data: dict,
) -> tuple[list[str], list[str]]:
    """Check referential integrity across config files.

    Returns (errors, warnings) tuple.
    """
    errors = []
    warnings = []

    members = members_data.get("members", [])
    if not isinstance(members, list):
        members = []
    member_usernames = {
        m.get("username") for m in members
        if isinstance(m, dict) and m.get("username")
    }

    teams = teams_data.get("teams", {})
    if not isinstance(teams, dict):
        teams = {}

    repos = repos_data.get("repositories", {})
    if not isinstance(repos, dict):
        repos = {}

    repo_names = set(repos.keys())

    # Check team members exist in members.yml
    for team_name, team_config in teams.items():
        if not isinstance(team_config, dict):
            continue

        for member in team_config.get("members", []):
            if not isinstance(member, dict):
                continue
            username = member.get("username", "")
            if username and username not in member_usernames:
                errors.append(
                    f"Team '{team_name}' references member '{username}' "
                    f"who is not in members.yml"
                )

        # Check team repos exist in repositories.yml (warning, not error)
        for repo_name in team_config.get("repos", {}):
            if repo_name not in repo_names:
                warnings.append(
                    f"Team '{team_name}' references repo '{repo_name}' "
                    f"which is not managed in repositories.yml (may be externally managed)"
                )

    # Check branch protection on private repos (free tier limitation)
    for repo_name, repo_config in repos.items():
        if not isinstance(repo_config, dict):
            continue
        visibility = repo_config.get("visibility", "public")
        branch_protection = repo_config.get("branch_protection", {})
        if visibility == "private" and branch_protection:
            warnings.append(
                f"Repository '{repo_name}' is private but has branch protection rules. "
                f"Branch protection requires a paid plan for private repos — "
                f"these rules will be skipped."
            )

    # Check for members not in any team
    members_in_teams = set()
    for team_config in teams.values():
        if not isinstance(team_config, dict):
            continue
        for member in team_config.get("members", []):
            if isinstance(member, dict):
                members_in_teams.add(member.get("username", ""))

    orphaned = member_usernames - members_in_teams
    for username in sorted(orphaned):
        warnings.append(
            f"Member '{username}' is not assigned to any team"
        )

    return errors, warnings


def validate_all(
    members_data: dict,
    teams_data: dict,
    repos_data: dict,
) -> tuple[list[str], list[str]]:
    """Run all validations. Returns (errors, warnings)."""
    errors = []
    warnings = []

    errors.extend(validate_members_config(members_data))
    errors.extend(validate_teams_config(teams_data))
    errors.extend(validate_repositories_config(repos_data))

    xref_errors, xref_warnings = validate_cross_references(
        members_data, teams_data, repos_data
    )
    errors.extend(xref_errors)
    warnings.extend(xref_warnings)

    return errors, warnings
