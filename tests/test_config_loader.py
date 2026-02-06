"""Tests for config loading and validation."""

import os
import sys
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from config_loader import load_config, load_members, load_teams, load_repositories
from models import MemberRole, TeamPrivacy, TeamMemberRole, RepoPermission, RepoVisibility


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestLoadMembers:
    def test_load_valid_members(self):
        raw, members = load_members(FIXTURES_DIR)
        assert len(members) == 3
        assert members[0].username == "alice"
        assert members[0].role == MemberRole.ADMIN
        assert members[1].username == "bob"
        assert members[1].role == MemberRole.MEMBER

    def test_member_defaults_to_member_role(self):
        raw, members = load_members(FIXTURES_DIR)
        # bob and charlie have explicit "member" role
        assert members[1].role == MemberRole.MEMBER
        assert members[2].role == MemberRole.MEMBER


class TestLoadTeams:
    def test_load_valid_teams(self):
        raw, teams = load_teams(FIXTURES_DIR)
        assert len(teams) == 2

        backend = next(t for t in teams if t.name == "backend")
        assert backend.description == "Backend engineering"
        assert backend.privacy == TeamPrivacy.CLOSED
        assert len(backend.members) == 2
        assert len(backend.repos) == 2

    def test_team_member_roles(self):
        raw, teams = load_teams(FIXTURES_DIR)
        backend = next(t for t in teams if t.name == "backend")
        alice = next(m for m in backend.members if m.username == "alice")
        assert alice.role == TeamMemberRole.MAINTAINER

    def test_team_repo_permissions(self):
        raw, teams = load_teams(FIXTURES_DIR)
        backend = next(t for t in teams if t.name == "backend")
        assert backend.repos["api-service"] == RepoPermission.PUSH
        assert backend.repos["shared-lib"] == RepoPermission.PULL

    def test_team_privacy(self):
        raw, teams = load_teams(FIXTURES_DIR)
        devops = next(t for t in teams if t.name == "devops")
        assert devops.privacy == TeamPrivacy.SECRET

    def test_team_slug_generation(self):
        raw, teams = load_teams(FIXTURES_DIR)
        backend = next(t for t in teams if t.name == "backend")
        assert backend.slug == "backend"


class TestLoadRepositories:
    def test_load_valid_repos(self):
        raw, repos = load_repositories(FIXTURES_DIR)
        assert len(repos) == 3

    def test_repo_with_branch_protection(self):
        raw, repos = load_repositories(FIXTURES_DIR)
        api = next(r for r in repos if r.name == "api-service")
        assert api.visibility == RepoVisibility.PUBLIC
        assert len(api.branch_protection) == 1
        bp = api.branch_protection[0]
        assert bp.branch == "main"
        assert bp.required_reviews == 1
        assert bp.dismiss_stale_reviews is True

    def test_repo_without_branch_protection(self):
        raw, repos = load_repositories(FIXTURES_DIR)
        lib = next(r for r in repos if r.name == "shared-lib")
        assert len(lib.branch_protection) == 0

    def test_private_repo(self):
        raw, repos = load_repositories(FIXTURES_DIR)
        infra = next(r for r in repos if r.name == "infra")
        assert infra.visibility == RepoVisibility.PRIVATE

    def test_repo_features(self):
        raw, repos = load_repositories(FIXTURES_DIR)
        api = next(r for r in repos if r.name == "api-service")
        assert api.has_issues is True
        assert api.has_wiki is False
        assert api.has_projects is False


class TestLoadConfig:
    def test_full_config_load(self):
        state, errors, warnings = load_config(
            config_dir=str(FIXTURES_DIR), validate=True
        )
        assert state.org_name == "test-org"
        assert len(state.members) == 3
        assert len(state.teams) == 2
        assert len(state.repositories) == 3
        assert len(errors) == 0

    def test_cross_reference_warnings(self):
        state, errors, warnings = load_config(
            config_dir=str(FIXTURES_DIR), validate=True
        )
        # charlie is not in any team
        charlie_warning = any("charlie" in w for w in warnings)
        assert charlie_warning

    def test_state_lookup_methods(self):
        state, _, _ = load_config(config_dir=str(FIXTURES_DIR), validate=False)
        assert state.get_member("alice") is not None
        assert state.get_member("nonexistent") is None
        assert state.get_team("backend") is not None
        assert state.get_repository("api-service") is not None
        assert "alice" in state.get_member_usernames()
