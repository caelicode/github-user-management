#!/usr/bin/env python3

import json
import os
import sys
import logging

def setup_workflow_logging():
    """Configure logging for workflow scripts."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )

def read_github_event():
    """
    Read and parse the GitHub event payload from GITHUB_EVENT_PATH.

    Returns:
        dict: The parsed event data

    Raises:
        SystemExit: If GITHUB_EVENT_PATH is not set or the file cannot be read
    """
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
    """
    Validate that a repository dispatch event contains required fields.

    Args:
        event_data (dict): The GitHub event data
        required_fields (list): List of required fields in client_payload

    Returns:
        dict: The client_payload if validation passes

    Raises:
        SystemExit: If validation fails
    """
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
    """
    Set a GitHub Actions output variable.
    Works with both the legacy ::set-output and the new $GITHUB_OUTPUT file approach.

    Args:
        name (str): Name of the output variable
        value (any): Value to set (will be converted to string or JSON)
    """
    # Convert value to JSON if it's not a string
    if not isinstance(value, str):
        value = json.dumps(value)

    # Check if we're using the new output file approach
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as f:
            f.write(f"{name}={value}\n")
    else:
        # Fall back to legacy ::set-output
        print(f"::set-output name={name}::{value}")
