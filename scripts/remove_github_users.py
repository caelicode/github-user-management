#!/usr/bin/env python3

import json
import os
import sys
import logging
import requests
import time
from datetime import datetime

def setup_logging():
    """Configure logging for the script."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"github_removal_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file)
        ]
    )
    return log_file

def get_usernames_from_env():
    """Get GitHub usernames from environment variable."""
    try:
        usernames_json = os.environ.get("USERNAMES_JSON", "[]")
        usernames = json.loads(usernames_json)

        if not usernames:
            logging.warning("No usernames found in USERNAMES_JSON environment variable")
            return []

        # Validate usernames
        invalid_usernames = []
        for username in usernames:
            if not isinstance(username, str) or ' ' in username or '@' in username or '/' in username:
                invalid_usernames.append(username)

        if invalid_usernames:
            logging.warning(f"Found {len(invalid_usernames)} invalid GitHub usernames: {invalid_usernames}")
            # Remove invalid usernames
            usernames = [u for u in usernames if u not in invalid_usernames]

        logging.info(f"Found {len(usernames)} valid GitHub usernames to process")
        return usernames

    except json.JSONDecodeError:
        logging.error("Failed to parse USERNAMES_JSON environment variable as JSON")
        return []
    except Exception as e:
        logging.error(f"Error getting usernames from environment: {str(e)}")
        return []

def check_user_in_org(session, username):
    """Check if a user exists in the cdcgov organization."""
    url = f"https://api.github.com/orgs/cdcgov/members/{username}"

    try:
        response = session.get(url)
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

def remove_user_from_org(session, username):
    """Remove a user from the cdcgov organization."""
    url = f"https://api.github.com/orgs/cdcgov/members/{username}"

    try:
        response = session.delete(url)
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

def send_callback_dispatch(token, results, usernames, test_mode):
    """Send callback dispatch to ocio-github-infra repository."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    # Create payload with feature branch info
    payload = {
        "event_type": "update_user_lists",
        "client_payload": {
            "usernames": usernames,
            "test_mode": test_mode,
            "cdcgov_processed": True,
            "success_count": results["success_count"],
            "failure_count": results["failure_count"],
            "job_status": "success" if results["failure_count"] == 0 else "failure",
            "ref": "github-off",  # Target github-off branch
            "feature_branch_test": True
        }
    }

    # Log payload (without token)
    logging.info(f"Sending callback dispatch to cdcent/ocio-github-infra")
    logging.info(f"Payload: {json.dumps(payload, indent=2)}")

    try:
        url = "https://api.github.com/repos/cdcent/ocio-github-infra/dispatches"
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 204:
            logging.info("✅ Callback dispatch sent successfully")
            return True
        else:
            logging.error(f"❌ Failed to send callback: {response.status_code}")
            logging.error(f"Response: {response.text}")
            return False
    except Exception as e:
        logging.error(f"Error sending callback: {str(e)}")
        return False

def main():
    log_file = setup_logging()
    logging.info("=== Starting GitHub User Removal from CDCGov Organization ===")

    # Get configuration from environment
    github_token = os.environ.get("GITHUB_TOKEN")
    callback_token = os.environ.get("CALLBACK_TOKEN")
    test_mode = os.environ.get("TEST_MODE", "false").lower() == "true"

    if not github_token:
        logging.error("GITHUB_TOKEN environment variable is required")
        sys.exit(1)

    # Set up session
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    })

    # Get usernames to process
    usernames = get_usernames_from_env()
    if not usernames:
        logging.warning("No users to process. Exiting.")
        sys.exit(0)

    # Initialize results
    results = {
        "success_count": 0,
        "failure_count": 0,
        "details": []
    }

    # Process each username
    logging.info(f"Processing {len(usernames)} users in {'TEST' if test_mode else 'PRODUCTION'} mode")

    for username in usernames:
        logging.info(f"\nProcessing user: {username}")

        # Check if user exists in organization
        in_org, check_error = check_user_in_org(session, username)

        if not in_org:
            if check_error == "User not found in organization":
                logging.info(f"User {username} is not in cdcgov organization")
                results["details"].append({
                    "username": username,
                    "success": True,
                    "message": "Not in organization"
                })
                results["success_count"] += 1
                continue
            else:
                logging.error(f"Error checking if {username} is in organization: {check_error}")
                results["details"].append({
                    "username": username,
                    "success": False,
                    "message": f"Check failed: {check_error}"
                })
                results["failure_count"] += 1
                continue

        # If we're in test mode, just log what would happen
        if test_mode:
            logging.info(f"TEST MODE: Would remove {username} from cdcgov organization")
            results["details"].append({
                "username": username,
                "success": True,
                "message": "Would remove (test mode)"
            })
            results["success_count"] += 1
            continue

        # Remove user from organization
        success, error = remove_user_from_org(session, username)

        if success:
            logging.info(f"✅ Successfully removed {username} from cdcgov organization")
            results["details"].append({
                "username": username,
                "success": True,
                "message": "Removed successfully"
            })
            results["success_count"] += 1
        else:
            logging.error(f"❌ Failed to remove {username} from cdcgov organization: {error}")
            results["details"].append({
                "username": username,
                "success": False,
                "message": f"Removal failed: {error}"
            })
            results["failure_count"] += 1

    # Write results to JSON file
    results_file = "removal_results.json"
    try:
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)
        logging.info(f"Wrote results to {results_file}")
    except Exception as e:
        logging.error(f"Failed to write results file: {str(e)}")

    # Summary
    logging.info("\n=== Removal Summary ===")
    logging.info(f"Total users processed: {len(usernames)}")
    logging.info(f"Success: {results['success_count']}")
    logging.info(f"Failures: {results['failure_count']}")
    logging.info(f"Mode: {'TEST' if test_mode else 'PRODUCTION'}")

    # Send callback if token is available
    if callback_token:
        callback_success = send_callback_dispatch(callback_token, results, usernames, test_mode)
        logging.info(f"Callback to update user lists: {'✅ Success' if callback_success else '❌ Failed'}")
    else:
        logging.warning("CALLBACK_TOKEN not provided. No callback will be sent.")

    # Create GitHub step summary if running in GitHub Actions
    github_step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if github_step_summary:
        try:
            with open(github_step_summary, "a") as f:
                f.write("## CDCGov GitHub User Removal Results\n\n")
                f.write(f"**Mode:** {'TEST' if test_mode else 'PRODUCTION'}\n\n")
                f.write(f"**Total users processed:** {len(usernames)}\n\n")
                f.write(f"**Success:** {results['success_count']}\n\n")
                f.write(f"**Failures:** {results['failure_count']}\n\n")

                if results["failure_count"] > 0:
                    f.write("### Failed Removals\n\n")
                    f.write("| Username | Error |\n")
                    f.write("|----------|-------|\n")
                    for detail in results["details"]:
                        if not detail["success"]:
                            f.write(f"| {detail['username']} | {detail['message']} |\n")
        except Exception as e:
            logging.error(f"Failed to write GitHub step summary: {str(e)}")

    # Exit with error code if any failures occurred
    if results["failure_count"] > 0:
        sys.exit(1)

    logging.info("✅ Process completed successfully")

if __name__ == "__main__":
    main()
