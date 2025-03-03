#!/usr/bin/env python3

import os
import json
import logging
from datetime import datetime

def setup_logging(prefix="github_removal"):
    """
    Configure logging for scripts.

    Args:
        prefix (str): Prefix for the log file name

    Returns:
        str: Path to the generated log file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"{prefix}_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file)
        ]
    )
    return log_file

def get_usernames_from_env(env_var="USERNAMES_JSON", default="[]"):
    """
    Get GitHub usernames from environment variable.

    Args:
        env_var (str): Name of the environment variable containing usernames
        default (str): Default value if environment variable is not set

    Returns:
        list: List of usernames
    """
    try:
        usernames_json = os.environ.get(env_var, default)

        # Debug log to help with troubleshooting
        logging.info(f"Raw {env_var} value: {usernames_json}")

        # Remove any surrounding quotes if present (handles possible quoting issues)
        if (usernames_json.startswith("'") and usernames_json.endswith("'")) or \
           (usernames_json.startswith('"') and usernames_json.endswith('"')):
            usernames_json = usernames_json[1:-1]

        usernames = json.loads(usernames_json)

        if not usernames:
            logging.warning(f"No usernames found in {env_var} environment variable")
            return []

        logging.info(f"Found {len(usernames)} usernames from environment")
        return usernames

    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse {env_var} environment variable as JSON: {e}")
        logging.error(f"Raw value: {usernames_json}")
        return []
    except Exception as e:
        logging.error(f"Error getting usernames: {str(e)}")
        return []

def write_results_file(filename, results):
    """
    Write operation results to a JSON file.

    Args:
        filename (str): Name of the output file
        results (dict): Results dictionary with success_count, failure_count, and details

    Returns:
        bool: True if file was written successfully, False otherwise
    """
    try:
        with open(filename, "w") as f:
            json.dump(results, f, indent=2)
        logging.info(f"Wrote results to {filename}")
        return True
    except Exception as e:
        logging.error(f"Error writing results file: {str(e)}")
        return False

def write_github_step_summary(results, usernames, test_mode, org_name="cdcgov"):
    """
    Write summary to GitHub Actions step summary.

    Args:
        results (dict): Results dictionary with success_count, failure_count, and details
        usernames (list): List of usernames processed
        test_mode (bool): Whether the operation was run in test mode
        org_name (str): Name of the GitHub organization
    """
    github_step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not github_step_summary:
        return

    try:
        with open(github_step_summary, "a") as f:
            f.write(f"## {org_name} GitHub User Removal Results\n\n")
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
        logging.error(f"Error writing GitHub step summary: {str(e)}")

def create_callback_payload(results, usernames, test_mode, feature_branch_test=True, ref="main"):
    """
    Create a payload for callback dispatch to update user lists.

    Args:
        results (dict): Results dictionary with success_count and failure_count
        usernames (list): List of usernames processed
        test_mode (bool): Whether the operation was run in test mode
        feature_branch_test (bool): Whether this is a test from a feature branch
        ref (str): Branch reference to use

    Returns:
        dict: Payload for the dispatch
    """
    return {
        "usernames": usernames,
        "test_mode": test_mode,
        "cdcgov_processed": True,
        "success_count": results["success_count"],
        "failure_count": results["failure_count"],
        "job_status": "success" if results["failure_count"] == 0 else "failure",
        "ref": ref,
        "feature_branch_test": feature_branch_test
    }
