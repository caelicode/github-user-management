#!/usr/bin/env python3

import os
import sys
import logging
from github_client import GitHubClient
from utils import (
    setup_logging,
    get_usernames_from_env,
    write_results_file,
    write_github_step_summary,
    create_callback_payload
)

def main():
    """
    Main entry point for the GitHub user removal script.
    Process users to be removed from the CDCgov GitHub organization.
    """
    # Set up logging
    log_file = setup_logging()

    # Log start of process
    logging.info("=== Starting GitHub User Removal from CDCGov Organization ===")

    # Get configuration from environment
    github_token = os.environ.get("GITHUB_TOKEN")
    callback_token = os.environ.get("CALLBACK_TOKEN")
    test_mode = os.environ.get("TEST_MODE", "false").lower() == "true"
    org_name = os.environ.get("ORG_NAME", "cdcgov")  # Default to cdcgov but allow override
    target_branch = os.environ.get("TARGET_BRANCH", "main")  # Branch for callback

    if not github_token:
        logging.error("GITHUB_TOKEN environment variable is required")
        sys.exit(1)

    # Create GitHub client
    github_client = GitHubClient(github_token)

    # Get usernames to process
    usernames = get_usernames_from_env()
    if not usernames:
        logging.warning("No users to process. Exiting.")
        sys.exit(0)

    # Validate usernames
    valid_usernames, invalid_usernames = github_client.validate_github_usernames(usernames)

    # Initialize results
    results = {
        "success_count": 0,
        "failure_count": 0,
        "details": []
    }

    # Process each username
    logging.info(f"Processing {len(valid_usernames)} users in {'TEST' if test_mode else 'PRODUCTION'} mode")

    for username in valid_usernames:
        logging.info(f"\nProcessing user: {username}")

        # Check if user exists in organization
        in_org, check_error = github_client.check_user_in_org(org_name, username)

        if not in_org:
            if check_error == "User not found in organization":
                logging.info(f"User {username} is not in {org_name} organization")
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
            logging.info(f"TEST MODE: Would remove {username} from {org_name} organization")
            results["details"].append({
                "username": username,
                "success": True,
                "message": "Would remove (test mode)"
            })
            results["success_count"] += 1
            continue

        # Remove user from organization
        success, error = github_client.remove_user_from_org(org_name, username)

        if success:
            logging.info(f"✅ Successfully removed {username} from {org_name} organization")
            results["details"].append({
                "username": username,
                "success": True,
                "message": "Removed successfully"
            })
            results["success_count"] += 1
        else:
            logging.error(f"❌ Failed to remove {username} from {org_name} organization: {error}")
            results["details"].append({
                "username": username,
                "success": False,
                "message": f"Removal failed: {error}"
            })
            results["failure_count"] += 1

    # Write results to JSON file
    results_file = "removal_results.json"
    write_results_file(results_file, results)

    # Summary
    logging.info("\n=== Removal Summary ===")
    logging.info(f"Total users processed: {len(valid_usernames)}")
    logging.info(f"Success: {results['success_count']}")
    logging.info(f"Failures: {results['failure_count']}")
    logging.info(f"Mode: {'TEST' if test_mode else 'PRODUCTION'}")

    # Send callback if token is available
    if callback_token:
        # Create callback payload
        callback_payload = create_callback_payload(
            results,
            valid_usernames,
            test_mode,
            feature_branch_test=True,
            ref=target_branch
        )

        # Send callback
        callback_success = github_client.send_callback_dispatch(
            callback_token,
            "cdcent",
            "ocio-github-infra",
            "update_user_lists",
            callback_payload
        )

        logging.info(f"Callback to update user lists: {'✅ Success' if callback_success else '❌ Failed'}")
    else:
        logging.warning("CALLBACK_TOKEN not provided. No callback will be sent.")

    # Write GitHub step summary
    write_github_step_summary(results, valid_usernames, test_mode, org_name)

    # Exit with error code if any failures occurred
    if results["failure_count"] > 0:
        sys.exit(1)

    logging.info("✅ Process completed successfully")

if __name__ == "__main__":
    main()
