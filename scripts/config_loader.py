#!/usr/bin/env python3

import logging
import os
from pathlib import Path
from typing import Optional

import yaml

from models import (
    BranchProtection,
    Member,
    MemberRole,
    OrgState,
    RepoPermission,
    RepoVisibility,
    Repository,
    Team,
    TeamMember,
    TeamMemberRole,
    TeamPrivacy,
)
from validators import validate_all


DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_yaml_file(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    if data is None:
        return {}

    return data


def load_members(config_dir: Path) -> tuple[dict, list[Member]]:
    raw = load_yaml_file(config_dir / "members.yml")
    members = []

    for entry in raw.get("members", []) or []:
        if not isinstance(entry, dict):
            continue
        members.append(Member(
            username=entry["username"],
            role=MemberRole(entry.get("role", "member")),
        ))

    return raw, members


def load_teams(config_dir: Path) -> tuple[dict, list[Team]]:
    raw = load_yaml_file(config_dir / "teams.yml")
    teams = []

    teams_data = raw.get("teams", {})
    if not isinstance(teams_data, dict):
        return raw, teams

    for team_name, team_config in teams_data.items():
        if not isinstance(team_config, dict):
            continue

        team_members = []
        for member in team_config.get("members", []) or []:
            if isinstance(member, dict):
                team_members.append(TeamMember(
                    username=member["username"],
                    role=TeamMemberRole(member.get("role", "member")),
                ))

        repos = {}
        for repo_name, perm in (team_config.get("repos", {}) or {}).items():
            repos[repo_name] = RepoPermission(perm)

        teams.append(Team(
            name=team_name,
            description=team_config.get("description", ""),
            privacy=TeamPrivacy(team_config.get("privacy", "closed")),
            members=team_members,
            repos=repos,
        ))

    return raw, teams


def load_repositories(config_dir: Path) -> tuple[dict, list[Repository]]:
    raw = load_yaml_file(config_dir / "repositories.yml")
    repositories = []

    repos_data = raw.get("repositories", {})
    if not isinstance(repos_data, dict):
        return raw, repositories

    for repo_name, repo_config in repos_data.items():
        if not isinstance(repo_config, dict):
            continue

        features = repo_config.get("features", {}) or {}
        branch_protections = []

        bp_config = repo_config.get("branch_protection", {}) or {}
        for branch_name, bp_rules in bp_config.items():
            if not isinstance(bp_rules, dict):
                continue
            branch_protections.append(BranchProtection(
                branch=branch_name,
                required_reviews=bp_rules.get("required_reviews", 1),
                dismiss_stale_reviews=bp_rules.get("dismiss_stale_reviews", True),
                require_status_checks=bp_rules.get("require_status_checks", False),
                required_status_contexts=bp_rules.get("required_status_contexts", []),
                enforce_admins=bp_rules.get("enforce_admins", False),
                restrict_pushes=bp_rules.get("restrict_pushes", False),
            ))

        repositories.append(Repository(
            name=repo_name,
            description=repo_config.get("description", ""),
            visibility=RepoVisibility(repo_config.get("visibility", "public")),
            default_branch=repo_config.get("default_branch", "main"),
            has_issues=features.get("has_issues", True),
            has_wiki=features.get("has_wiki", False),
            has_projects=features.get("has_projects", False),
            branch_protection=branch_protections,
        ))

    return raw, repositories


def load_org_name(config_dir: Path) -> str:
    raw = load_yaml_file(config_dir / "org.yml")
    org_config = raw.get("organization", {})
    return org_config.get("name", "")


def load_config(
    config_dir: Optional[str] = None,
    validate: bool = True,
) -> tuple[OrgState, list[str], list[str]]:
    if config_dir:
        config_path = Path(config_dir)
    else:
        config_path = DEFAULT_CONFIG_DIR

    logging.info(f"Loading config from: {config_path}")

    org_name = load_org_name(config_path)
    if not org_name:
        return OrgState(org_name=""), ["Organization name not set in org.yml"], []

    members_raw, members = load_members(config_path)
    teams_raw, teams = load_teams(config_path)
    repos_raw, repositories = load_repositories(config_path)

    errors = []
    warnings = []

    if validate:
        errors, warnings = validate_all(members_raw, teams_raw, repos_raw)

    state = OrgState(
        org_name=org_name,
        members=members,
        teams=teams,
        repositories=repositories,
    )

    logging.info(
        f"Config loaded: {len(members)} members, "
        f"{len(teams)} teams, {len(repositories)} repositories"
    )

    return state, errors, warnings
