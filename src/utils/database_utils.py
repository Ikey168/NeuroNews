"""Database utility functions."""
import os
import json
from pathlib import Path


def get_redshift_connection_params():
    """
    Load Redshift connection parameters from a config file.
    """
    env = os.environ.get("ENV", "dev")
    config_path = Path(f"config/{env}_aws.json")
    if not config_path.exists():
        return {}
    with open(config_path, "r") as f:
        try:
            config = json.load(f)
            return config.get("redshift", {})
        except json.JSONDecodeError:
            return {}
