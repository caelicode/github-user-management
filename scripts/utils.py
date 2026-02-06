#!/usr/bin/env python3

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def setup_logging(prefix: str = "org_sync") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"{prefix}_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file),
        ],
    )
    return log_file


def write_results_file(filename: str, results: Any) -> bool:
    try:
        with open(filename, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logging.info(f"Wrote results to {filename}")
        return True
    except Exception as e:
        logging.error(f"Error writing results file: {e}")
        return False


def load_yaml_file(path: str) -> dict:
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return data if data is not None else {}
    except FileNotFoundError:
        logging.error(f"File not found: {path}")
        return {}
    except yaml.YAMLError as e:
        logging.error(f"YAML parse error in {path}: {e}")
        return {}


def get_usernames_from_env(env_var: str = "USERNAMES_JSON", default: str = "[]") -> list[str]:
    try:
        raw = os.environ.get(env_var, default)
        logging.info(f"Raw {env_var} value: {raw}")

        if (raw.startswith("'") and raw.endswith("'")) or \
           (raw.startswith('"') and raw.endswith('"')):
            raw = raw[1:-1]

        usernames = json.loads(raw)

        if not isinstance(usernames, list):
            logging.error(f"{env_var} is not a valid array: {raw}")
            return []

        return [u for u in usernames if isinstance(u, str)]
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse {env_var} as JSON: {e}")
        return []
    except Exception as e:
        logging.error(f"Error reading {env_var}: {e}")
        return []
