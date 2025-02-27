#!/usr/bin/env python3
import os
import json
import logging
import requests
import sys

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )

def main():
    setup_logging()

    # Get environment variables
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logging.error("GITHUB_TOKEN not provided")
        sys.exit(1)

    test_mode = os.environ.get("TEST_MODE", "false").lower() == "true"

    try:
        usernames = json.loads(os.environ.get("USERNAMES_JSON", "[]"))
    except json.JSONDecodeError:
        logging.error("Invalid JSON in USERNAMES_JSON")
        sys.exit(1)

    if not usernames:
        logging.info("No usernames to process")
        sys.exit(0)

    logging.info(f"Processing {len(usernames)} users in {'TEST' if test_mode else 'PRODUCTION'} mode")

    # Set up API session
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    })

    success_count = 0
    failure_count = 0

    for username in usernames:
        logging.info(f"Processing user: {username}")

        # Check if user exists in org first
        check_url = f"https://api.github.com/orgs/cdcgov/members/{username}"
        check_resp = session.get(check_url)

        if check_resp.status_code == 204:
            logging.info(f"User {username} confirmed in cdcgov organization")

            if test_mode:
                logging.info(f"TEST MODE: Would remove {username} from cdcgov")
                success_count += 1
            else:
                # Perform actual removal
                resp = session.delete(check_url)

                if resp.status_code == 204:
                    logging.info(f"✅ Successfully removed {username} from cdcgov")
                    success_count += 1
                else:
                    logging.error(f"❌ Failed to remove {username}. Status: {resp.status_code}")
                    logging.error(f"Response: {resp.text}")
                    failure_count += 1
        elif check_resp.status_code == 404:
            logging.info(f"User {username} not found in cdcgov organization")
            success_count += 1  # Count as success since the user is already not in the org
        else:
            logging.error(f"Error checking membership for {username}. Status: {check_resp.status_code}")
            logging.error(f"Response: {check_resp.text}")
            failure_count += 1

    logging.info(f"Summary: Success={success_count}, Failed={failure_count}")

    if failure_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
