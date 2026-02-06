#!/usr/bin/env python3

import json
import os
import sys
import logging

def setup_workflow_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )

def read_github_event():
    event_path = os.environ.get('GITHUB_EVENT_PATH')
    if not event_path:
        logging.error("GITHUB_EVENT_PATH not found")
        sys.exit(1)

    logging.info(f"Reading event from: {event_path}")

    try:
        with open(event_path, 'r', encoding='utf-8') as f:
            event_data = json.load(f)
        return event_data
    except Exception as e:
        logging.error(f"Error reading event payload: {e}")
        sys.exit(1)

def validate_dispatch_payload(event_data, required_fields=None):
    if required_fields is None:
        required_fields = ['usernames', 'test_mode']

    logging.info("Event details:")
    logging.info(f"Event name: {os.environ.get('GITHUB_EVENT_NAME')}")
    logging.info(f"Event action: {event_data.get('action')}")

    client_payload = event_data.get('client_payload', {})
    logging.info(f"Client payload: {json.dumps(client_payload, indent=2)}")

    missing_fields = [field for field in required_fields if field not in client_payload]

    if missing_fields:
        logging.error(f"Missing required fields in client_payload: {missing_fields}")
        sys.exit(1)

    return client_payload

def set_github_output(name, value):
    if not isinstance(value, str):
        value = json.dumps(value)

    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as f:
            f.write(f"{name}={value}\n")
    else:
        print(f"::set-output name={name}::{value}")
