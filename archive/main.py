#!/usr/bin/env python3

import os
import sys
import json
import time
import logging
from datetime import datetime

from github_client import GitHubClient
from utils import setup_logging, get_usernames_from_env, write_results_file, create_callback_payload
from workflow_utils import set_github_output

def main():

    setup_logging("github_removal")

    logging.info("=== Starting GitHub User Removal from CDCGov Organization ===")

    usernames = get_usernames_from_env()
    if not usernames:
        logging.error("No usernames provided. Exiting.")
        sys.exit(1)

    test_mode = os.environ.get('TEST_MODE', 'true').lower() == 'true'
    callback_repo = os.environ.get('CALLBACK_REPO', '')
    callback_event = os.environ.get('CALLBACK_EVENT', 'update_user_lists')

    mode = "TEST" if test_mode else "LIVE"
    logging.info(f"Processing {len(usernames)} users in {mode} mode")

    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token:
        logging.error("No GitHub token found in environment")
        sys.exit(1)

    github = GitHubClient(github_token)

    successful_users = []
    failed_users = []

    for username in usernames:
        logging.info(f"\nProcessing user: {username}")
        success, message = github.remove_user_from_org("cdcgov", username, test_mode)

        if success:
            successful_users.append({"username": username, "message": message, "success": True})
        else:
            failed_users.append({"username": username, "message": message, "success": False})

    results = {
        "timestamp": datetime.now().isoformat(),
        "test_mode": test_mode,
        "org": "cdcgov",
        "success_count": len(successful_users),
        "failure_count": len(failed_users),
        "details": successful_users + failed_users
    }

    write_results_file("removal_results.json", results)

    logging.info("\n=== Removal Summary ===")
    logging.info(f"Total users processed: {len(usernames)}")
    logging.info(f"Success: {len(successful_users)}")
    logging.info(f"Failures: {len(failed_users)}")
    logging.info(f"Mode: {'TEST' if test_mode else 'PRODUCTION'}")

    logging.info("Waiting 5 seconds before sending callback...")
    time.sleep(5)

    if callback_repo:
        logging.info(f"Sending callback to update user lists in {callback_repo}")

        payload = create_callback_payload(
            results=results,
            usernames=usernames,
            test_mode=test_mode,
            feature_branch_test=os.environ.get('feature_branch_test', 'true').lower() == 'true',
            ref=os.environ.get('ref', 'main')
        )

        callback_token = os.environ.get('CALLBACK_TOKEN')
        if not callback_token:
            logging.error("No callback token found in environment")
            sys.exit(1)

        success = github.send_repository_dispatch(
            owner=callback_repo.split('/')[0],
            repo=callback_repo.split('/')[1],
            event_type=callback_event,
            client_payload=payload,
            token=callback_token
        )

        if not success:
            logging.error("Callback to update user lists: Failed")
            sys.exit(1)

        logging.info("Callback sent successfully")
    else:
        logging.info("No callback repo configured, skipping callback")

    logging.info("Process completed successfully")
    return 0

if __name__ == "__main__":
    sys.exit(main())
