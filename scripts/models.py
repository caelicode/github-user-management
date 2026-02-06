#!/usr/bin/env python3
"""Data models for GitHub organization management.

Provides type-safe representations of all organization resources
including members, teams, repositories, and sync operations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional


# --- Enums ---

class MemberRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"

class TeamPrivacy(str, Enum):
    CLOSED = "closed"
    SECRET = "secret"

class TeamMemberRole(str, Enum):
    MAINTAINER = "maintainer"
    MEMBER = "member"

class RepoPermission(str, Enum):
    PULL = "pull"
    TRIAGE = "triage"
    PUSH = "push"
    MAINTAIN = "maintain"
    ADMIN = "admin"

class RepoVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"

class ActionType(str, Enum):
    # Members
    MEMBER_INVITE = "member_invite"
    MEMBER_REMOVE = "member_remove"
    MEMBER_UPDATE_ROLE = "member_update_role"
    # Teams
    TEAM_CREATE = "team_create"
    TEAM_UPDATE = "team_update"
    TEAM_DELETE = "team_delete"
    # Team membership
    TEAM_MEMBER_ADD = "team_member_add"
    TEAM_MEMBER_REMOVE = "team_member_remove"
    TEAM_MEMBER_UPDATE_ROLE = "team_member_update_role"
    # Team-repo permissions
    TEAM_REPO_ADD = "team_repo_add"
    TEAM_REPO_REMOVE = "team_repo_remove"
    TEAM_REPO_UPDATE = "team_repo_update"
    # Repository settings
    REPO_UPDATE = "repo_update"
    # Branch protection
    BRANCH_PROTECTION_SET = "branch_protection_set"
    BRANCH_PROTECTION_DELETE = "branch_protection_delete"

class ActionStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# --- Organization Resources ---

@dataclass
class Member:
    username: str
    role: MemberRole = MemberRole.MEMBER

    def to_dict(self) -> dict:
        return {"username": self.username, "role": self.role.value}


@dataclass
class TeamMember:
    username: str
    role: TeamMemberRole = TeamMemberRole.MEMBER

    def to_dict(self) -> dict:
        return {"username": self.username, "role": self.role.value}


@dataclass
class BranchProtection:
    branch: str
    required_reviews: int = 1
    dismiss_stale_reviews: bool = True
    require_status_checks: bool = False
    required_status_contexts: list[str] = field(default_factory=list)
    enforce_admins: bool = False
    restrict_pushes: bool = False

    def to_dict(self) -> dict:
        return {
            "branch": self.branch,
            "required_reviews": self.required_reviews,
            "dismiss_stale_reviews": self.dismiss_stale_reviews,
            "require_status_checks": self.require_status_checks,
            "required_status_contexts": self.required_status_contexts,
            "enforce_admins": self.enforce_admins,
            "restrict_pushes": self.restrict_pushes,
        }

    def to_api_payload(self) -> dict:
        """Convert to GitHub API branch protection payload."""
        payload: dict[str, Any] = {
            "required_pull_request_reviews": {
                "required_approving_review_count": self.required_reviews,
                "dismiss_stale_reviews": self.dismiss_stale_reviews,
            },
            "enforce_admins": self.enforce_admins,
            "restrictions": None,
        }
        if self.require_status_checks:
            payload["required_status_checks"] = {
                "strict": True,
                "contexts": self.required_status_contexts,
            }
        else:
            payload["required_status_checks"] = None

        return payload


@dataclass
class Repository:
    name: str
    description: str = ""
    visibility: RepoVisibility = RepoVisibility.PUBLIC
    default_branch: str = "main"
    has_issues: bool = True
    has_wiki: bool = False
    has_projects: bool = False
    branch_protection: list[BranchProtection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "visibility": self.visibility.value,
            "default_branch": self.default_branch,
            "has_issues": self.has_issues,
            "has_wiki": self.has_wiki,
            "has_projects": self.has_projects,
            "branch_protection": [bp.to_dict() for bp in self.branch_protection],
        }


@dataclass
class Team:
    name: str
    slug: str = ""
    description: str = ""
    privacy: TeamPrivacy = TeamPrivacy.CLOSED
    members: list[TeamMember] = field(default_factory=list)
    repos: dict[str, RepoPermission] = field(default_factory=dict)

    def __post_init__(self):
        if not self.slug:
            self.slug = self.name.lower().replace(" ", "-")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "privacy": self.privacy.value,
            "members": [m.to_dict() for m in self.members],
            "repos": {k: v.value for k, v in self.repos.items()},
        }


# --- State Representations ---

@dataclass
class OrgState:
    """Complete state of an organization — desired or actual."""
    org_name: str
    members: list[Member] = field(default_factory=list)
    teams: list[Team] = field(default_factory=list)
    repositories: list[Repository] = field(default_factory=list)

    def get_member(self, username: str) -> Optional[Member]:
        return next((m for m in self.members if m.username == username), None)

    def get_team(self, name: str) -> Optional[Team]:
        return next((t for t in self.teams if t.name == name), None)

    def get_team_by_slug(self, slug: str) -> Optional[Team]:
        return next((t for t in self.teams if t.slug == slug), None)

    def get_repository(self, name: str) -> Optional[Repository]:
        return next((r for r in self.repositories if r.name == name), None)

    def get_member_usernames(self) -> set[str]:
        return {m.username for m in self.members}

    def get_team_names(self) -> set[str]:
        return {t.name for t in self.teams}

    def to_dict(self) -> dict:
        return {
            "org_name": self.org_name,
            "members": [m.to_dict() for m in self.members],
            "teams": [t.to_dict() for t in self.teams],
            "repositories": [r.to_dict() for r in self.repositories],
        }


# --- Sync Operations ---

@dataclass
class SyncAction:
    """A single action to reconcile desired vs actual state."""
    action_type: ActionType
    resource: str
    details: dict = field(default_factory=dict)
    priority: int = 5
    status: ActionStatus = ActionStatus.PENDING
    message: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type.value,
            "resource": self.resource,
            "details": self.details,
            "priority": self.priority,
            "status": self.status.value,
            "message": self.message,
            "error": self.error,
        }

    @property
    def symbol(self) -> str:
        """Symbol for plan output (Terraform-style)."""
        symbols = {
            ActionType.MEMBER_INVITE: "+",
            ActionType.MEMBER_REMOVE: "-",
            ActionType.MEMBER_UPDATE_ROLE: "~",
            ActionType.TEAM_CREATE: "+",
            ActionType.TEAM_UPDATE: "~",
            ActionType.TEAM_DELETE: "-",
            ActionType.TEAM_MEMBER_ADD: "+",
            ActionType.TEAM_MEMBER_REMOVE: "-",
            ActionType.TEAM_MEMBER_UPDATE_ROLE: "~",
            ActionType.TEAM_REPO_ADD: "+",
            ActionType.TEAM_REPO_REMOVE: "-",
            ActionType.TEAM_REPO_UPDATE: "~",
            ActionType.REPO_UPDATE: "~",
            ActionType.BRANCH_PROTECTION_SET: "+",
            ActionType.BRANCH_PROTECTION_DELETE: "-",
        }
        return symbols.get(self.action_type, "?")

    @property
    def description(self) -> str:
        """Human-readable description of the action."""
        descriptions = {
            ActionType.MEMBER_INVITE: f"Invite `{self.resource}` as `{self.details.get('role', 'member')}`",
            ActionType.MEMBER_REMOVE: f"Remove `{self.resource}` from organization",
            ActionType.MEMBER_UPDATE_ROLE: f"Update `{self.resource}` role: `{self.details.get('from')}` → `{self.details.get('to')}`",
            ActionType.TEAM_CREATE: f"Create team `{self.resource}` ({self.details.get('privacy', 'closed')})",
            ActionType.TEAM_UPDATE: f"Update team `{self.resource}`",
            ActionType.TEAM_DELETE: f"Delete team `{self.resource}`",
            ActionType.TEAM_MEMBER_ADD: f"Add `{self.details.get('username')}` to `{self.resource}` as `{self.details.get('role', 'member')}`",
            ActionType.TEAM_MEMBER_REMOVE: f"Remove `{self.details.get('username')}` from `{self.resource}`",
            ActionType.TEAM_MEMBER_UPDATE_ROLE: f"Update `{self.details.get('username')}` in `{self.resource}`: `{self.details.get('from')}` → `{self.details.get('to')}`",
            ActionType.TEAM_REPO_ADD: f"Grant `{self.resource}` → `{self.details.get('repo')}` ({self.details.get('permission')})",
            ActionType.TEAM_REPO_REMOVE: f"Revoke `{self.resource}` access to `{self.details.get('repo')}`",
            ActionType.TEAM_REPO_UPDATE: f"Update `{self.resource}` → `{self.details.get('repo')}`: `{self.details.get('from')}` → `{self.details.get('to')}`",
            ActionType.REPO_UPDATE: f"Update repository `{self.resource}` settings",
            ActionType.BRANCH_PROTECTION_SET: f"Set branch protection on `{self.resource}` / `{self.details.get('branch')}`",
            ActionType.BRANCH_PROTECTION_DELETE: f"Remove branch protection from `{self.resource}` / `{self.details.get('branch')}`",
        }
        return descriptions.get(self.action_type, f"{self.action_type.value} on {self.resource}")


@dataclass
class SyncPlan:
    """A complete plan of actions to synchronize an organization."""
    actions: list[SyncAction] = field(default_factory=list)
    timestamp: str = ""
    org_name: str = ""
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"

    @property
    def sorted_actions(self) -> list[SyncAction]:
        return sorted(self.actions, key=lambda a: a.priority)

    @property
    def adds(self) -> list[SyncAction]:
        return [a for a in self.actions if a.symbol == "+"]

    @property
    def updates(self) -> list[SyncAction]:
        return [a for a in self.actions if a.symbol == "~"]

    @property
    def removes(self) -> list[SyncAction]:
        return [a for a in self.actions if a.symbol == "-"]

    @property
    def has_changes(self) -> bool:
        return len(self.actions) > 0

    @property
    def estimated_api_calls(self) -> int:
        return len(self.actions)

    @property
    def summary(self) -> str:
        return f"{len(self.adds)} to add, {len(self.updates)} to change, {len(self.removes)} to remove"

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "org_name": self.org_name,
            "summary": self.summary,
            "has_changes": self.has_changes,
            "estimated_api_calls": self.estimated_api_calls,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "actions": [a.to_dict() for a in self.sorted_actions],
        }


@dataclass
class SyncResult:
    """Result of executing a sync plan."""
    plan: SyncPlan
    executed_at: str = ""
    dry_run: bool = False
    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0

    def __post_init__(self):
        if not self.executed_at:
            self.executed_at = datetime.utcnow().isoformat() + "Z"

    @property
    def success(self) -> bool:
        return self.failure_count == 0

    def to_dict(self) -> dict:
        return {
            "executed_at": self.executed_at,
            "dry_run": self.dry_run,
            "success": self.success,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "skipped_count": self.skipped_count,
            "plan": self.plan.to_dict(),
        }


# --- Security Audit ---

@dataclass
class SecurityFinding:
    """A security concern found during audit."""
    severity: str  # high, medium, low
    category: str
    resource: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)
