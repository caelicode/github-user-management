#!/usr/bin/env python3

import logging
import requests

class GitHubClient:
    """Client for interacting with GitHub API for organization management."""

    def __init__(self, token):
        """Initialize GitHub client with authorization token."""
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        })

    def check_user_in_org(self, org_name, username):
        """
        Check if a user exists in the specified GitHub organization.

        Args:
            org_name (str): Name of the GitHub organization
            username (str): GitHub username to check

        Returns:
            tuple: (is_member, error_message)
                - is_member (bool): True if user is a member, False otherwise
                - error_message (str): Error message if any, None if successful
        """
        url = f"https://api.github.com/orgs/{org_name}/members/{username}"

        try:
            response = self.session.get(url)
            if response.status_code == 204:
                # User exists in organization
                return True, None
            elif response.status_code == 404:
                # User does not exist in organization
                return False, "User not found in organization"
            else:
                # Unexpected response
                error_message = f"Unexpected response: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_message += f" - {error_data['message']}"
                except:
                    pass
                return False, error_message
        except Exception as e:
            return False, f"Exception checking membership: {str(e)}"

    def remove_user_from_org(self, org_name, username):
        """
        Remove a user from the specified GitHub organization.

        Args:
            org_name (str): Name of the GitHub organization
            username (str): GitHub username to remove

        Returns:
            tuple: (success, error_message)
                - success (bool): True if removal was successful, False otherwise
                - error_message (str): Error message if any, None if successful
        """
        url = f"https://api.github.com/orgs/{org_name}/members/{username}"

        try:
            response = self.session.delete(url)
            if response.status_code == 204:
                # Success
                return True, None
            elif response.status_code == 404:
                # User already not in organization
                return True, "User not found in organization (already removed)"
            else:
                # Error
                error_message = f"Failed with status code: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_message += f" - {error_data['message']}"
                except:
                    pass
                return False, error_message
        except Exception as e:
            return False, f"Exception during removal: {str(e)}"

    def send_callback_dispatch(self, token, repo_owner, repo_name, event_type, client_payload):
        """
        Send a repository dispatch event to another repository.

        Args:
            token (str): GitHub API token with permissions for the target repository
            repo_owner (str): Owner of the target repository
            repo_name (str): Name of the target repository
            event_type (str): Type of dispatch event
            client_payload (dict): Payload to send with the dispatch

        Returns:
            bool: True if dispatch was successful, False otherwise
        """
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28"
        }

        # Ensure client_payload contains the required fields
        if not client_payload:
            client_payload = {}

        payload = {
            "event_type": event_type,
            "client_payload": client_payload
        }

        # Log payload (without token)
        logging.info(f"Sending dispatch to {repo_owner}/{repo_name}")
        logging.info(f"Payload: {payload}")

        try:
            url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/dispatches"
            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 204:
                logging.info(f"✅ Dispatch to {repo_owner}/{repo_name} successful")
                return True
            else:
                logging.error(f"❌ Failed to send dispatch: {response.status_code}")
                logging.error(f"Response: {response.text}")
                return False
        except Exception as e:
            logging.error(f"Error sending dispatch: {str(e)}")
            return False

    def validate_github_usernames(self, usernames):
        """
        Validate GitHub usernames against basic format requirements.

        Args:
            usernames (list): List of usernames to validate

        Returns:
            list: List of valid usernames
            list: List of invalid usernames
        """
        valid_usernames = []
        invalid_usernames = []

        for username in usernames:
            if not isinstance(username, str) or ' ' in username or '@' in username or '/' in username:
                invalid_usernames.append(username)
            else:
                valid_usernames.append(username)

        if invalid_usernames:
            logging.warning(f"Found {len(invalid_usernames)} invalid GitHub usernames: {invalid_usernames}")

        return valid_usernames, invalid_usernames
