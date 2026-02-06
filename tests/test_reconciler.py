"""Tests for the reconciliation engine (diffing logic)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from models import (
    ActionType,
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
from reconciler import Reconciler


class FakeGitHubClient:
    """Minimal fake client for testing diff logic without API calls."""
    pass


def make_reconciler(org="test-org"):
    return Reconciler(FakeGitHubClient(), org)


class TestDiffMembers:
    def test_new_member_detected(self):
        r = make_reconciler()
        desired = OrgState(
            org_name="test-org",
            members=[Member("alice", MemberRole.ADMIN)],
        )
        current = OrgState(org_name="test-org")
        plan = r.diff(desired, current)
        assert len(plan.actions) == 1
        assert plan.actions[0].action_type == ActionType.MEMBER_INVITE
        assert plan.actions[0].resource == "alice"

    def test_removed_member_detected(self):
        r = make_reconciler()
        desired = OrgState(org_name="test-org")
        current = OrgState(
            org_name="test-org",
            members=[Member("alice", MemberRole.MEMBER)],
        )
        plan = r.diff(desired, current)
        assert len(plan.actions) == 1
        assert plan.actions[0].action_type == ActionType.MEMBER_REMOVE

    def test_role_change_detected(self):
        r = make_reconciler()
        desired = OrgState(
            org_name="test-org",
            members=[Member("alice", MemberRole.ADMIN)],
        )
        current = OrgState(
            org_name="test-org",
            members=[Member("alice", MemberRole.MEMBER)],
        )
        plan = r.diff(desired, current)
        assert len(plan.actions) == 1
        assert plan.actions[0].action_type == ActionType.MEMBER_UPDATE_ROLE
        assert plan.actions[0].details["from"] == "member"
        assert plan.actions[0].details["to"] == "admin"

    def test_no_change_when_in_sync(self):
        r = make_reconciler()
        members = [Member("alice", MemberRole.ADMIN)]
        desired = OrgState(org_name="test-org", members=members.copy())
        current = OrgState(org_name="test-org", members=members.copy())
        plan = r.diff(desired, current)
        member_actions = [
            a for a in plan.actions
            if a.action_type in (
                ActionType.MEMBER_INVITE,
                ActionType.MEMBER_REMOVE,
                ActionType.MEMBER_UPDATE_ROLE,
            )
        ]
        assert len(member_actions) == 0


class TestDiffTeams:
    def test_new_team_detected(self):
        r = make_reconciler()
        desired = OrgState(
            org_name="test-org",
            teams=[Team(name="backend", description="Backend team")],
        )
        current = OrgState(org_name="test-org")
        plan = r.diff(desired, current)
        team_actions = [a for a in plan.actions if a.action_type == ActionType.TEAM_CREATE]
        assert len(team_actions) == 1
        assert team_actions[0].resource == "backend"

    def test_deleted_team_detected(self):
        r = make_reconciler()
        desired = OrgState(org_name="test-org")
        current = OrgState(
            org_name="test-org",
            teams=[Team(name="old-team", description="Old")],
        )
        plan = r.diff(desired, current)
        delete_actions = [a for a in plan.actions if a.action_type == ActionType.TEAM_DELETE]
        assert len(delete_actions) == 1

    def test_team_description_update(self):
        r = make_reconciler()
        desired = OrgState(
            org_name="test-org",
            teams=[Team(name="backend", description="Updated desc")],
        )
        current = OrgState(
            org_name="test-org",
            teams=[Team(name="backend", description="Old desc")],
        )
        plan = r.diff(desired, current)
        update_actions = [a for a in plan.actions if a.action_type == ActionType.TEAM_UPDATE]
        assert len(update_actions) == 1


class TestDiffTeamMembership:
    def test_new_team_member(self):
        r = make_reconciler()
        desired = OrgState(
            org_name="test-org",
            teams=[Team(
                name="backend",
                members=[TeamMember("alice", TeamMemberRole.MAINTAINER)],
            )],
        )
        current = OrgState(
            org_name="test-org",
            teams=[Team(name="backend")],
        )
        plan = r.diff(desired, current)
        add_actions = [a for a in plan.actions if a.action_type == ActionType.TEAM_MEMBER_ADD]
        assert len(add_actions) == 1
        assert add_actions[0].details["username"] == "alice"

    def test_removed_team_member(self):
        r = make_reconciler()
        desired = OrgState(
            org_name="test-org",
            teams=[Team(name="backend")],
        )
        current = OrgState(
            org_name="test-org",
            teams=[Team(
                name="backend",
                members=[TeamMember("alice")],
            )],
        )
        plan = r.diff(desired, current)
        remove_actions = [a for a in plan.actions if a.action_type == ActionType.TEAM_MEMBER_REMOVE]
        assert len(remove_actions) == 1


class TestDiffTeamRepos:
    def test_new_team_repo(self):
        r = make_reconciler()
        desired = OrgState(
            org_name="test-org",
            teams=[Team(
                name="backend",
                repos={"api": RepoPermission.PUSH},
            )],
        )
        current = OrgState(
            org_name="test-org",
            teams=[Team(name="backend")],
        )
        plan = r.diff(desired, current)
        add_actions = [a for a in plan.actions if a.action_type == ActionType.TEAM_REPO_ADD]
        assert len(add_actions) == 1
        assert add_actions[0].details["repo"] == "api"
        assert add_actions[0].details["permission"] == "push"

    def test_permission_change(self):
        r = make_reconciler()
        desired = OrgState(
            org_name="test-org",
            teams=[Team(
                name="backend",
                repos={"api": RepoPermission.ADMIN},
            )],
        )
        current = OrgState(
            org_name="test-org",
            teams=[Team(
                name="backend",
                repos={"api": RepoPermission.PUSH},
            )],
        )
        plan = r.diff(desired, current)
        update_actions = [a for a in plan.actions if a.action_type == ActionType.TEAM_REPO_UPDATE]
        assert len(update_actions) == 1
        assert update_actions[0].details["from"] == "push"
        assert update_actions[0].details["to"] == "admin"


class TestDiffBranchProtection:
    def test_new_branch_protection(self):
        r = make_reconciler()
        desired = OrgState(
            org_name="test-org",
            repositories=[Repository(
                name="api",
                visibility=RepoVisibility.PUBLIC,
                branch_protection=[BranchProtection(branch="main")],
            )],
        )
        current = OrgState(
            org_name="test-org",
            repositories=[Repository(
                name="api",
                visibility=RepoVisibility.PUBLIC,
            )],
        )
        plan = r.diff(desired, current)
        bp_actions = [a for a in plan.actions if a.action_type == ActionType.BRANCH_PROTECTION_SET]
        assert len(bp_actions) == 1

    def test_private_repo_skipped_with_warning(self):
        r = make_reconciler()
        desired = OrgState(
            org_name="test-org",
            repositories=[Repository(
                name="private-repo",
                visibility=RepoVisibility.PRIVATE,
                branch_protection=[BranchProtection(branch="main")],
            )],
        )
        current = OrgState(org_name="test-org")
        plan = r.diff(desired, current)
        bp_actions = [a for a in plan.actions if a.action_type == ActionType.BRANCH_PROTECTION_SET]
        assert len(bp_actions) == 0
        assert any("private" in w.lower() for w in plan.warnings)


class TestPlanProperties:
    def test_plan_summary(self):
        r = make_reconciler()
        desired = OrgState(
            org_name="test-org",
            members=[
                Member("alice", MemberRole.ADMIN),
                Member("new-user", MemberRole.MEMBER),
            ],
        )
        current = OrgState(
            org_name="test-org",
            members=[
                Member("alice", MemberRole.ADMIN),
                Member("leaving", MemberRole.MEMBER),
            ],
        )
        plan = r.diff(desired, current)
        assert plan.has_changes
        assert "1 to add" in plan.summary
        assert "1 to remove" in plan.summary

    def test_sorted_actions_by_priority(self):
        r = make_reconciler()
        desired = OrgState(
            org_name="test-org",
            members=[Member("new-user", MemberRole.MEMBER)],
            teams=[Team(
                name="team",
                members=[TeamMember("new-user")],
                repos={"repo": RepoPermission.PUSH},
            )],
        )
        current = OrgState(org_name="test-org")
        plan = r.diff(desired, current)
        priorities = [a.priority for a in plan.sorted_actions]
        assert priorities == sorted(priorities)
