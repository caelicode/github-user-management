#!/usr/bin/env python3

import logging
import time
from typing import Any, Optional

import requests


class GitHubClient:

    BASE_URL = "https://api.github.com"
    MAX_RETRIES = 3
    RETRY_BACKOFF = 2

    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> requests.Response:
        if not url.startswith("http"):
            url = f"{self.BASE_URL}{url}"

        last_exception = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.session.request(method, url, **kwargs)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logging.warning(f"Rate limited. Waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                if response.status_code >= 500:
                    wait = self.RETRY_BACKOFF * (2 ** attempt)
                    logging.warning(
                        f"Server error {response.status_code}. "
                        f"Retrying in {wait}s (attempt {attempt + 1}/{self.MAX_RETRIES})"
                    )
                    time.sleep(wait)
                    continue

                return response

            except requests.exceptions.RequestException as e:
                last_exception = e
                wait = self.RETRY_BACKOFF * (2 ** attempt)
                logging.warning(f"Request failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)

        if last_exception:
            raise last_exception
        return response

    def _paginated_get(self, url: str, params: dict = None) -> list[dict]:
        if params is None:
            params = {}
        params.setdefault("per_page", 100)

        all_items = []

        while url:
            response = self._request_with_retry("GET", url, params=params)

            if response.status_code != 200:
                logging.error(f"GET {url} failed: {response.status_code}")
                break

            items = response.json()
            if isinstance(items, list):
                all_items.extend(items)
            else:
                break

            link_header = response.headers.get("Link", "")
            url = None
            params = {}
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
                    break

        return all_items

    def _extract_error(self, response: requests.Response) -> str:
        try:
            data = response.json()
            msg = data.get("message", "")
            errors = data.get("errors", [])
            if errors:
                details = "; ".join(
                    e.get("message", str(e)) for e in errors
                )
                return f"{msg} ({details})" if msg else details
            return msg
        except Exception:
            return response.text[:200] if response.text else f"HTTP {response.status_code}"

    def get_rate_limit(self) -> dict:
        response = self._request_with_retry("GET", "/rate_limit")
        if response.status_code == 200:
            data = response.json()
            core = data.get("resources", {}).get("core", {})
            logging.info(
                f"Rate limit: {core.get('remaining')}/{core.get('limit')} "
                f"(resets at {core.get('reset')})"
            )
            return core
        return {}

    def list_org_members(self, org: str) -> list[dict]:
        members = self._paginated_get(f"/orgs/{org}/members")
        result = []
        for member in members:
            username = member.get("login", "")
            role = self._get_member_role(org, username)
            result.append({
                "username": username,
                "role": role,
                "id": member.get("id"),
            })
        return result

    def _get_member_role(self, org: str, username: str) -> str:
        response = self._request_with_retry(
            "GET", f"/orgs/{org}/memberships/{username}"
        )
        if response.status_code == 200:
            return response.json().get("role", "member")
        return "member"

    def check_user_membership(self, org: str, username: str) -> tuple[bool, Optional[str]]:
        response = self._request_with_retry(
            "GET", f"/orgs/{org}/members/{username}"
        )
        if response.status_code == 204:
            return True, None
        elif response.status_code == 404:
            return False, "User not found in organization"
        elif response.status_code == 302:
            return True, None
        else:
            return False, self._extract_error(response)

    def invite_member(
        self, org: str, username: str, role: str = "member"
    ) -> tuple[bool, str]:
        response = self._request_with_retry(
            "PUT",
            f"/orgs/{org}/memberships/{username}",
            json={"role": role},
        )
        if response.status_code in (200, 201):
            state = response.json().get("state", "unknown")
            if state == "active":
                return True, f"Membership updated to {role}"
            return True, f"Invitation sent ({state})"
        else:
            return False, self._extract_error(response)

    def remove_member(self, org: str, username: str) -> tuple[bool, str]:
        response = self._request_with_retry(
            "DELETE", f"/orgs/{org}/members/{username}"
        )
        if response.status_code == 204:
            return True, "Removed from organization"
        elif response.status_code == 404:
            return True, "User was not in organization"
        else:
            return False, self._extract_error(response)

    def list_teams(self, org: str) -> list[dict]:
        return self._paginated_get(f"/orgs/{org}/teams")

    def get_team_by_slug(self, org: str, slug: str) -> Optional[dict]:
        response = self._request_with_retry(
            "GET", f"/orgs/{org}/teams/{slug}"
        )
        if response.status_code == 200:
            return response.json()
        return None

    def create_team(
        self,
        org: str,
        name: str,
        description: str = "",
        privacy: str = "closed",
    ) -> tuple[bool, str]:
        response = self._request_with_retry(
            "POST",
            f"/orgs/{org}/teams",
            json={
                "name": name,
                "description": description,
                "privacy": privacy,
            },
        )
        if response.status_code in (201, 200):
            slug = response.json().get("slug", name)
            return True, f"Team created (slug: {slug})"
        elif response.status_code == 422:
            return False, f"Validation failed: {self._extract_error(response)}"
        else:
            return False, self._extract_error(response)

    def update_team(
        self,
        org: str,
        team_slug: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        privacy: Optional[str] = None,
    ) -> tuple[bool, str]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if privacy is not None:
            payload["privacy"] = privacy

        if not payload:
            return True, "No changes needed"

        response = self._request_with_retry(
            "PATCH", f"/orgs/{org}/teams/{team_slug}", json=payload
        )
        if response.status_code == 200:
            return True, "Team updated"
        else:
            return False, self._extract_error(response)

    def delete_team(self, org: str, team_slug: str) -> tuple[bool, str]:
        response = self._request_with_retry(
            "DELETE", f"/orgs/{org}/teams/{team_slug}"
        )
        if response.status_code == 204:
            return True, "Team deleted"
        elif response.status_code == 404:
            return True, "Team did not exist"
        else:
            return False, self._extract_error(response)

    def list_team_members(self, org: str, team_slug: str) -> list[dict]:
        members = self._paginated_get(f"/orgs/{org}/teams/{team_slug}/members")
        result = []
        for member in members:
            username = member.get("login", "")
            role_response = self._request_with_retry(
                "GET",
                f"/orgs/{org}/teams/{team_slug}/memberships/{username}",
            )
            role = "member"
            if role_response.status_code == 200:
                role = role_response.json().get("role", "member")
            result.append({"username": username, "role": role})
        return result

    def add_team_member(
        self,
        org: str,
        team_slug: str,
        username: str,
        role: str = "member",
    ) -> tuple[bool, str]:
        response = self._request_with_retry(
            "PUT",
            f"/orgs/{org}/teams/{team_slug}/memberships/{username}",
            json={"role": role},
        )
        if response.status_code == 200:
            state = response.json().get("state", "active")
            return True, f"Added to team ({state}, role: {role})"
        else:
            return False, self._extract_error(response)

    def remove_team_member(
        self, org: str, team_slug: str, username: str
    ) -> tuple[bool, str]:
        response = self._request_with_retry(
            "DELETE",
            f"/orgs/{org}/teams/{team_slug}/memberships/{username}",
        )
        if response.status_code == 204:
            return True, "Removed from team"
        elif response.status_code == 404:
            return True, "User was not in team"
        else:
            return False, self._extract_error(response)

    def list_team_repos(self, org: str, team_slug: str) -> list[dict]:
        repos = self._paginated_get(f"/orgs/{org}/teams/{team_slug}/repos")
        result = []
        for repo in repos:
            permissions = repo.get("permissions", {})
            perm = "pull"
            if permissions.get("admin"):
                perm = "admin"
            elif permissions.get("maintain"):
                perm = "maintain"
            elif permissions.get("push"):
                perm = "push"
            elif permissions.get("triage"):
                perm = "triage"

            result.append({
                "name": repo.get("name", ""),
                "full_name": repo.get("full_name", ""),
                "permission": perm,
            })
        return result

    def add_team_repo(
        self,
        org: str,
        team_slug: str,
        repo_name: str,
        permission: str = "push",
    ) -> tuple[bool, str]:
        response = self._request_with_retry(
            "PUT",
            f"/orgs/{org}/teams/{team_slug}/repos/{org}/{repo_name}",
            json={"permission": permission},
        )
        if response.status_code == 204:
            return True, f"Team granted {permission} access to {repo_name}"
        else:
            return False, self._extract_error(response)

    def remove_team_repo(
        self, org: str, team_slug: str, repo_name: str
    ) -> tuple[bool, str]:
        response = self._request_with_retry(
            "DELETE",
            f"/orgs/{org}/teams/{team_slug}/repos/{org}/{repo_name}",
        )
        if response.status_code == 204:
            return True, f"Team access to {repo_name} removed"
        elif response.status_code == 404:
            return True, "Team did not have access"
        else:
            return False, self._extract_error(response)

    def list_org_repos(self, org: str) -> list[dict]:
        return self._paginated_get(f"/orgs/{org}/repos", {"type": "all"})

    def get_repo(self, owner: str, repo: str) -> Optional[dict]:
        response = self._request_with_retry(
            "GET", f"/repos/{owner}/{repo}"
        )
        if response.status_code == 200:
            return response.json()
        return None

    def update_repo(
        self,
        owner: str,
        repo: str,
        settings: dict,
    ) -> tuple[bool, str]:
        response = self._request_with_retry(
            "PATCH", f"/repos/{owner}/{repo}", json=settings
        )
        if response.status_code == 200:
            return True, "Repository settings updated"
        else:
            return False, self._extract_error(response)

    def get_branch_protection(
        self, owner: str, repo: str, branch: str
    ) -> Optional[dict]:
        response = self._request_with_retry(
            "GET", f"/repos/{owner}/{repo}/branches/{branch}/protection"
        )
        if response.status_code == 200:
            return response.json()
        return None

    def set_branch_protection(
        self,
        owner: str,
        repo: str,
        branch: str,
        rules: dict,
    ) -> tuple[bool, str]:
        response = self._request_with_retry(
            "PUT",
            f"/repos/{owner}/{repo}/branches/{branch}/protection",
            json=rules,
        )
        if response.status_code == 200:
            return True, f"Branch protection set on {branch}"
        elif response.status_code == 403:
            return False, "Insufficient permissions (private repo on free plan?)"
        elif response.status_code == 404:
            return False, f"Branch '{branch}' not found"
        else:
            return False, self._extract_error(response)

    def delete_branch_protection(
        self, owner: str, repo: str, branch: str
    ) -> tuple[bool, str]:
        response = self._request_with_retry(
            "DELETE",
            f"/repos/{owner}/{repo}/branches/{branch}/protection",
        )
        if response.status_code == 204:
            return True, f"Branch protection removed from {branch}"
        elif response.status_code == 404:
            return True, "No branch protection was set"
        else:
            return False, self._extract_error(response)

    def send_repository_dispatch(
        self,
        owner: str,
        repo: str,
        event_type: str,
        client_payload: dict,
        token: Optional[str] = None,
    ) -> bool:
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/dispatches"
        headers = dict(self.session.headers)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload = {
            "event_type": event_type,
            "client_payload": client_payload,
        }

        try:
            response = self.session.post(url, json=payload, headers=headers)
            if response.status_code == 204:
                return True
            logging.error(f"Dispatch failed: {response.status_code} {response.text}")
            return False
        except Exception as e:
            logging.error(f"Dispatch error: {e}")
            return False
