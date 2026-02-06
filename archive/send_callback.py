#!/usr/bin/env python3

import os
import sys
import json
import logging
import requests

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )

def fix_json_formatting(raw_json_str):
    if not raw_json_str:
        return []

    try:
        return json.loads(raw_json_str)
    except json.JSONDecodeError:
        pass

    logging.info(f"Attempting to fix malformed JSON: {raw_json_str}")

    fixed = raw_json_str.strip()

    fixed = fixed.replace('[', '["').replace(']', '"]')
    fixed = fixed.replace(',', '", "').replace('  ', ' ')
    fixed = fixed.replace('" "', '", "')

    import re
    fixed = re.sub(r'\s+', ' ', fixed)

    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        logging.warning("Manual extraction of usernames")
        usernames = []
        import re
        matches = re.findall(r'[a-zA-Z0-9_-]+', raw_json_str)
        return [m for m in matches if len(m) > 1]

def get_callback_info():
    event_path = os.environ.get('GITHUB_EVENT_PATH')
    if not event_path:
        logging.error("GITHUB_EVENT_PATH not found")
        return None, None

    try:
        with open(event_path, 'r') as f:
            event_data = json.load(f)

        client_payload = event_data.get('client_payload', {})
        callback_repo = client_payload.get('callback_repo', '')
        callback_event = client_payload.get('callback_event', 'update_user_lists')

        if not callback_repo:
            logging.info("No callback repository specified")
            return None, None

        return callback_repo, callback_event
    except Exception as e:
        logging.error(f"Error reading event payload: {e}")
        return None, None

def send_callback():
    setup_logging()

    callback_repo, callback_event = get_callback_info()
    if not callback_repo:
        logging.info("No callback needed, exiting successfully")
        return 0

    if len(sys.argv) < 4:
        logging.error("Usage: send_callback.py <completion_status> <test_mode> <processed_usernames_json>")
        return 1

    completion_status = sys.argv[1]
    test_mode = sys.argv[2].lower() == 'true'
    raw_usernames = sys.argv[3]

    processed_usernames = fix_json_formatting(raw_usernames)

    logging.info(f"Sending callback to {callback_repo}")
    logging.info(f"Event: {callback_event}")
    logging.info(f"Status: {completion_status}")
    logging.info(f"Test mode: {test_mode}")
    logging.info(f"Processed usernames: {processed_usernames}")

    callback_token = os.environ.get('CALLBACK_TOKEN')
    if not callback_token:
        logging.error("CALLBACK_TOKEN not found in environment")
        return 1

    payload = {
        "event_type": callback_event,
        "client_payload": {
            "cdcgov_processed": True,
            "test_mode": test_mode,
            "job_status": completion_status,
            "usernames": processed_usernames
        }
    }

    headers = {
        "Authorization": f"Bearer {callback_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        logging.info("Sending callback...")
        response = requests.post(
            f"https://api.github.com/repos/{callback_repo}/dispatches",
            json=payload,
            headers=headers
        )

        if response.status_code == 204:
            logging.info("Callback sent successfully")
            return 0
        else:
            logging.error(f"Callback failed with status code: {response.status_code}")
            logging.error(f"Response: {response.text}")
            return 1
    except Exception as e:
        logging.error(f"Error sending callback: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(send_callback())
