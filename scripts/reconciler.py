#!/usr/bin/env python3
"""Reconciliation engine for GitHub organization management.

Compares desired state (from config files) against actual state (from GitHub API)
and produces an ordered plan of actions to bring the org into alignment.
All operations are idempotent — safe to re-run.
"""

import logging
from typing import Optional

from github_client import GitHubClient
from models import (
    ActionStatus,
    ActionType,
    BranchProtection,
    Member,
    MemberRole,
    OrgState,
    RepoPermission,
    RepoVisibility,
    Repository,
    SecurityFinding,
    SyncAction,
    SyncPlan,
    SyncResult,
    Team,
    TeamMember,
    TeamMemberRole,
    TeamPrivacy,
)


class Reconciler:
    """Compares desired and actual org state, generates and executes sync plans."""

    def __init__(self, client: GitHubClient, org_name: str):
        self.client = client
        self.org_name = org_name

    # ------------------------------------------------------------------ #
    #  Fetch current state from GitHub                                    #
    # ------------------------------------------------------------------ #

    def fetch_current_state(self) -> OrgState:
        """Query GitHub API to build the actual current state of the org."""
        logging.info(f"Fetching current state of '{self.org_name}' from GitHub...")

        state = OrgState(org_name=self.org_name)

        # Members
        logging.info("  Fetching members...")
        raw_members = self.client.list_org_members(self.org_name)
        for m in raw_members:
            state.members.append(Member(
                username=m["username"],
                role=MemberRole(m.get("role", "member")),
            ))
        logging.info(f"  Found {len(state.members)} members")

        # Teams
        logging.info("  Fetching teams...")
        raw_teams = self.client.list_teams(self.org_name)
        for t in raw_teams:
            slug = t.get("slug", "")
            team = Team(
                name=t.get("name", slug),
                slug=slug,
                description=t.get("description", "") or "",
                privacy=TeamPrivacy(t.get("privacy", "closed")),
            )

            # Team members
            raw_team_members = self.client.list_team_members(self.org_name, slug)
            for tm in raw_team_members:
                team.members.append(TeamMember(
                    username=tm["username"],
                    role=TeamMemberRole(tm.get("role", "member")),
                ))

            # Team repos
            raw_team_repos = self.client.list_team_repos(self.org_name, slug)
            for tr in raw_team_repos:
                team.repos[tr["name"]] = RepoPermission(tr["permission"])

            state.teams.append(team)
        logging.info(f"  Found {len(state.teams)} teams")

        # Repositories
        logging.info("  Fetching repositories...")
        raw_repos = self.client.list_org_repos(self.org_name)
        for r in raw_repos:
            repo = Repository(
                name=r.get("name", ""),
                description=r.get("description", "") or "",
                visibility=RepoVisibility(
                    "private" if r.get("private") else "public"
                ),
                default_branch=r.get("default_branch", "main"),
                has_issues=r.get("has_issues", True),
                has_wiki=r.get("has_wiki", False),
                has_projects=r.get("has_projects", False),
            )

            # Branch protection (only for public repos on free plan)
            if repo.visibility == RepoVisibility.PUBLIC:
                bp = self.client.get_branch_protection(
                    self.org_name, repo.name, repo.default_branch
                )
                if bp:
                    pr_reviews = bp.get("required_pull_request_reviews", {}) or {}
                    status_checks = bp.get("required_status_checks", {}) or {}
                    repo.branch_protection.append(BranchProtection(
                        branch=repo.default_branch,
                        required_reviews=pr_reviews.get(
                            "required_approving_review_count", 1
                        ),
                        dismiss_stale_reviews=pr_reviews.get(
                            "dismiss_stale_reviews", False
                        ),
                        require_status_checks=bool(status_checks),
                        required_status_contexts=status_checks.get("contexts", []),
                        enforce_admins=bp.get("enforce_admins", {}).get(
                            "enabled", False
                        ),
                    ))

            state.repositories.append(repo)
        logging.info(f"  Found {len(state.repositories)} repositories")

        return state

    # ------------------------------------------------------------------ #
    #  Generate diff / sync plan                                          #
    # ------------------------------------------------------------------ #

    def diff(self, desired: OrgState, current: OrgState) -> SyncPlan:
        """Compare desired and current state, produce an ordered action plan."""
        plan = SyncPlan(org_name=self.org_name)

        self._diff_members(desired, current, plan)
        self._diff_teams(desired, current, plan)
        self._diff_team_memberships(desired, current, plan)
        self._diff_team_repos(desired, current, plan)
        self._diff_branch_protection(desired, current, plan)

        logging.info(f"Plan generated: {plan.summary}")
        return plan

    def _diff_members(
        self, desired: OrgState, current: OrgState, plan: SyncPlan
    ):
        """Diff org members — add, remove, or update roles."""
        desired_map = {m.username: m for m in desired.members}
        current_map = {m.username: m for m in current.members}

        # Members to add
        for username, member in desired_map.items():
            if username not in current_map:
                plan.actions.append(SyncAction(
                    action_type=ActionType.MEMBER_INVITE,
                    resource=username,
                    details={"role": member.role.value},
                    priority=1,
                ))

        # Members to remove
        for username in current_map:
            if username not in desired_map:
                plan.actions.append(SyncAction(
                    action_type=ActionType.MEMBER_REMOVE,
                    resource=username,
                    priority=7,
                ))

        # Members with role changes
        for username, member in desired_map.items():
            if username in current_map:
                current_role = current_map[username].role
                if member.role != current_role:
                    plan.actions.append(SyncAction(
                        action_type=ActionType.MEMBER_UPDATE_ROLE,
                        resource=username,
                        details={
                            "from": current_role.value,
                            "to": member.role.value,
                        },
                        priority=6,
                    ))

    def _diff_teams(
        self, desired: OrgState, current: OrgState, plan: SyncPlan
    ):
        """Diff teams — create, update, or delete."""
        desired_slugs = {t.slug: t for t in desired.teams}
        current_slugs = {t.slug: t for t in current.teams}

        # Teams to create
        for slug, team in desired_slugs.items():
            if slug not in current_slugs:
                plan.actions.append(SyncAction(
                    action_type=ActionType.TEAM_CREATE,
                    resource=team.name,
                    details={
                        "description": team.description,
                        "privacy": team.privacy.value,
                    },
                    priority=2,
                ))

        # Teams to delete
        for slug, team in current_slugs.items():
            if slug not in desired_slugs:
                plan.actions.append(SyncAction(
                    action_type=ActionType.TEAM_DELETE,
                    resource=team.name,
                    details={"slug": slug},
                    priority=8,
                ))
                plan.warnings.append(
                    f"Team '{team.name}' will be deleted. "
                    f"This removes all team permissions."
                )

        # Teams to update (description or privacy changed)
        for slug, team in desired_slugs.items():
            if slug in current_slugs:
                current_team = current_slugs[slug]
                changes = {}
                if team.description != current_team.description:
                    changes["description"] = {
                        "from": current_team.description,
                        "to": team.description,
                    }
                if team.privacy != current_team.privacy:
                    changes["privacy"] = {
                        "from": current_team.privacy.value,
                        "to": team.privacy.value,
                    }
                if changes:
                    plan.actions.append(SyncAction(
                        action_type=ActionType.TEAM_UPDATE,
                        resource=team.name,
                        details=changes,
                        priority=2,
                    ))

    def _diff_team_memberships(
        self, desired: OrgState, current: OrgState, plan: SyncPlan
    ):
        """Diff team memberships — add, remove, or update roles within teams."""
        desired_slugs = {t.slug: t for t in desired.teams}
        current_slugs = {t.slug: t for t in current.teams}

        for slug, desired_team in desired_slugs.items():
            desired_members = {m.username: m for m in desired_team.members}

            # For existing teams, compare membership
            if slug in current_slugs:
                current_members = {
                    m.username: m for m in current_slugs[slug].members
                }
            else:
                current_members = {}

            # Members to add to team
            for username, member in desired_members.items():
                if username not in current_members:
                    plan.actions.append(SyncAction(
                        action_type=ActionType.TEAM_MEMBER_ADD,
                        resource=desired_team.name,
                        details={
                            "username": username,
                            "role": member.role.value,
                            "team_slug": slug,
                        },
                        priority=3,
                    ))

            # Members to remove from team
            for username in current_members:
                if username not in desired_members:
                    plan.actions.append(SyncAction(
                        action_type=ActionType.TEAM_MEMBER_REMOVE,
                        resource=desired_team.name,
                        details={
                            "username": username,
                            "team_slug": slug,
                        },
                        priority=3,
                    ))

            # Members with role changes
            for username, member in desired_members.items():
                if username in current_members:
                    current_role = current_members[username].role
                    if member.role != current_role:
                        plan.actions.append(SyncAction(
                            action_type=ActionType.TEAM_MEMBER_UPDATE_ROLE,
                            resource=desired_team.name,
                            details={
                                "username": username,
                                "team_slug": slug,
                                "from": current_role.value,
                                "to": member.role.value,
                            },
                            priority=3,
                        ))

    def _diff_team_repos(
        self, desired: OrgState, current: OrgState, plan: SyncPlan
    ):
        """Diff team-repository permissions."""
        desired_slugs = {t.slug: t for t in desired.teams}
        current_slugs = {t.slug: t for t in current.teams}

        for slug, desired_team in desired_slugs.items():
            desired_repos = desired_team.repos

            if slug in current_slugs:
                current_repos = current_slugs[slug].repos
            else:
                current_repos = {}

            # Repos to add to team
            for repo_name, perm in desired_repos.items():
                if repo_name not in current_repos:
                    plan.actions.append(SyncAction(
                        action_type=ActionType.TEAM_REPO_ADD,
                        resource=desired_team.name,
                        details={
                            "repo": repo_name,
                            "permission": perm.value,
                            "team_slug": slug,
                        },
                        priority=4,
                    ))
                elif current_repos[repo_name] != perm:
                    plan.actions.append(SyncAction(
                        action_type=ActionType.TEAM_REPO_UPDATE,
                        resource=desired_team.name,
                        details={
                            "repo": repo_name,
                            "team_slug": slug,
                            "from": current_repos[repo_name].value,
                            "to": perm.value,
                        },
                        priority=4,
                    ))

            # Repos to remove from team
            for repo_name in current_repos:
                if repo_name not in desired_repos:
                    plan.actions.append(SyncAction(
                        action_type=ActionType.TEAM_REPO_REMOVE,
                        resource=desired_team.name,
                        details={
                            "repo": repo_name,
                            "team_slug": slug,
                        },
                        priority=4,
                    ))

    def _diff_branch_protection(
        self, desired: OrgState, current: OrgState, plan: SyncPlan
    ):
        """Diff branch protection rules (public repos only)."""
        for desired_repo in desired.repositories:
            if desired_repo.visibility != RepoVisibility.PUBLIC:
                if desired_repo.branch_protection:
                    plan.warnings.append(
                        f"Skipping branch protection for private repo "
                        f"'{desired_repo.name}' (requires paid plan)"
                    )
                continue

            current_repo = current.get_repository(desired_repo.name)
            current_bps = {}
            if current_repo:
                current_bps = {bp.branch: bp for bp in current_repo.branch_protection}

            for desired_bp in desired_repo.branch_protection:
                if desired_bp.branch not in current_bps:
                    plan.actions.append(SyncAction(
                        action_type=ActionType.BRANCH_PROTECTION_SET,
                        resource=desired_repo.name,
                        details={
                            "branch": desired_bp.branch,
                            "rules": desired_bp.to_dict(),
                        },
                        priority=5,
                    ))
                else:
                    current_bp = current_bps[desired_bp.branch]
                    if self._bp_differs(desired_bp, current_bp):
                        plan.actions.append(SyncAction(
                            action_type=ActionType.BRANCH_PROTECTION_SET,
                            resource=desired_repo.name,
                            details={
                                "branch": desired_bp.branch,
                                "rules": desired_bp.to_dict(),
                            },
                            priority=5,
                        ))

    def _bp_differs(self, a: BranchProtection, b: BranchProtection) -> bool:
        """Check if two branch protection configs differ."""
        return (
            a.required_reviews != b.required_reviews
            or a.dismiss_stale_reviews != b.dismiss_stale_reviews
            or a.require_status_checks != b.require_status_checks
            or a.enforce_admins != b.enforce_admins
            or a.restrict_pushes != b.restrict_pushes
            or set(a.required_status_contexts) != set(b.required_status_contexts)
        )

    # ------------------------------------------------------------------ #
    #  Execute a sync plan                                                #
    # ------------------------------------------------------------------ #

    def apply(self, plan: SyncPlan, dry_run: bool = False) -> SyncResult:
        """Execute all actions in a sync plan.

        Actions are executed in priority order. Individual failures
        don't stop the overall process — each action is logged.
        """
        result = SyncResult(plan=plan, dry_run=dry_run)

        if not plan.has_changes:
            logging.info("No changes to apply — organization is in sync.")
            return result

        mode = "DRY RUN" if dry_run else "LIVE"
        logging.info(f"Applying plan ({mode}): {plan.summary}")

        for action in plan.sorted_actions:
            if dry_run:
                action.status = ActionStatus.SKIPPED
                action.message = f"[DRY RUN] Would execute: {action.description}"
                logging.info(f"  {action.symbol} {action.message}")
                result.skipped_count += 1
                continue

            try:
                success, message = self._execute_action(action)
                if success:
                    action.status = ActionStatus.SUCCESS
                    action.message = message
                    result.success_count += 1
                    logging.info(f"  {action.symbol} {action.description}: {message}")
                else:
                    action.status = ActionStatus.FAILED
                    action.error = message
                    result.failure_count += 1
                    logging.error(
                        f"  ! {action.description}: FAILED — {message}"
                    )
            except Exception as e:
                action.status = ActionStatus.FAILED
                action.error = str(e)
                result.failure_count += 1
                logging.error(f"  ! {action.description}: EXCEPTION — {e}")

        logging.info(
            f"Apply complete: {result.success_count} succeeded, "
            f"{result.failure_count} failed, {result.skipped_count} skipped"
        )

        return result

    def _execute_action(self, action: SyncAction) -> tuple[bool, str]:
        """Execute a single sync action against the GitHub API."""
        org = self.org_name
        d = action.details

        dispatch = {
            ActionType.MEMBER_INVITE: lambda: self.client.invite_member(
                org, action.resource, d.get("role", "member")
            ),
            ActionType.MEMBER_REMOVE: lambda: self.client.remove_member(
                org, action.resource
            ),
            ActionType.MEMBER_UPDATE_ROLE: lambda: self.client.invite_member(
                org, action.resource, d.get("to", "member")
            ),
            ActionType.TEAM_CREATE: lambda: self.client.create_team(
                org, action.resource, d.get("description", ""),
                d.get("privacy", "closed")
            ),
            ActionType.TEAM_UPDATE: lambda: self.client.update_team(
                org, d.get("slug", action.resource.lower().replace(" ", "-")),
                description=d.get("description", {}).get("to"),
                privacy=d.get("privacy", {}).get("to"),
            ),
            ActionType.TEAM_DELETE: lambda: self.client.delete_team(
                org, d.get("slug", action.resource.lower().replace(" ", "-"))
            ),
            ActionType.TEAM_MEMBER_ADD: lambda: self.client.add_team_member(
                org, d["team_slug"], d["username"], d.get("role", "member")
            ),
            ActionType.TEAM_MEMBER_REMOVE: lambda: self.client.remove_team_member(
                org, d["team_slug"], d["username"]
            ),
            ActionType.TEAM_MEMBER_UPDATE_ROLE: lambda: self.client.add_team_member(
                org, d["team_slug"], d["username"], d.get("to", "member")
            ),
            ActionType.TEAM_REPO_ADD: lambda: self.client.add_team_repo(
                org, d["team_slug"], d["repo"], d.get("permission", "push")
            ),
            ActionType.TEAM_REPO_REMOVE: lambda: self.client.remove_team_repo(
                org, d["team_slug"], d["repo"]
            ),
            ActionType.TEAM_REPO_UPDATE: lambda: self.client.add_team_repo(
                org, d["team_slug"], d["repo"], d.get("to", "push")
            ),
            ActionType.BRANCH_PROTECTION_SET: lambda: self._apply_branch_protection(
                action
            ),
            ActionType.BRANCH_PROTECTION_DELETE: lambda: self.client.delete_branch_protection(
                org, action.resource, d["branch"]
            ),
        }

        handler = dispatch.get(action.action_type)
        if handler:
            return handler()
        return False, f"Unknown action type: {action.action_type}"

    def _apply_branch_protection(self, action: SyncAction) -> tuple[bool, str]:
        """Apply branch protection rules from action details."""
        rules = action.details.get("rules", {})
        bp = BranchProtection(
            branch=rules.get("branch", action.details.get("branch", "main")),
            required_reviews=rules.get("required_reviews", 1),
            dismiss_stale_reviews=rules.get("dismiss_stale_reviews", True),
            require_status_checks=rules.get("require_status_checks", False),
            required_status_contexts=rules.get("required_status_contexts", []),
            enforce_admins=rules.get("enforce_admins", False),
        )
        return self.client.set_branch_protection(
            self.org_name, action.resource, bp.branch, bp.to_api_payload()
        )

    # ------------------------------------------------------------------ #
    #  Security Audit                                                     #
    # ------------------------------------------------------------------ #

    def security_audit(self, current: OrgState) -> list[SecurityFinding]:
        """Run security checks against the current org state."""
        findings = []

        # Check for excessive admin count
        admins = [m for m in current.members if m.role == MemberRole.ADMIN]
        if len(admins) > max(2, len(current.members) // 3):
            findings.append(SecurityFinding(
                severity="medium",
                category="access_control",
                resource="organization",
                message=(
                    f"{len(admins)} of {len(current.members)} members have admin role. "
                    f"Consider limiting admin access."
                ),
            ))

        # Check for public repos without branch protection
        for repo in current.repositories:
            if repo.visibility == RepoVisibility.PUBLIC:
                if not repo.branch_protection:
                    findings.append(SecurityFinding(
                        severity="high",
                        category="branch_protection",
                        resource=repo.name,
                        message=(
                            f"Public repo '{repo.name}' has no branch protection "
                            f"on any branch."
                        ),
                    ))

        # Check for empty teams
        for team in current.teams:
            if not team.members:
                findings.append(SecurityFinding(
                    severity="low",
                    category="housekeeping",
                    resource=team.name,
                    message=f"Team '{team.name}' has no members (stale team?).",
                ))

        # Check for repos not managed by any team
        repos_in_teams = set()
        for team in current.teams:
            repos_in_teams.update(team.repos.keys())
        for repo in current.repositories:
            if repo.name not in repos_in_teams:
                findings.append(SecurityFinding(
                    severity="low",
                    category="housekeeping",
                    resource=repo.name,
                    message=(
                        f"Repo '{repo.name}' is not managed by any team (orphaned)."
                    ),
                ))

        return findings
