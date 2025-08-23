#!/usr/bin/env python3

"""
Neptune Failover Configuration Manager
This script helps configure the application to use Neptune replica endpoints for disaster recovery
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional


class NeptuneFailoverManager:
    """Manages Neptune endpoint configuration for failover scenarios."""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)

        # Configuration files
        self.dr_config_file = self.config_dir / "disaster_recovery.json"
        self.original_config_file = self.config_dir / "original_endpoints.json"

        # Logging setup
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def save_original_config(self) -> bool:
        """Save current Neptune configuration for rollback."""
        try:
            original_config = {
                "neptune_endpoint": os.getenv("NEPTUNE_ENDPOINT"),
                "neptune_host": os.getenv("NEPTUNE_HOST"),
                "neptune_port": os.getenv("NEPTUNE_PORT", "8182"),
                "timestamp": "2025-06-07T00:00:00Z",
            }

            with open(self.original_config_file, "w") as f:
                json.dump(original_config, f, indent=2)

            self.logger.info(
                f" Original configuration saved to {self.original_config_file}"
            )
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to save original config: {e}")
            return False

    def create_failover_config(
        self, primary_endpoint: str, replica_endpoint: str, mode: str = "replica"
    ) -> bool:
        """Create disaster recovery configuration."""
        try:
            dr_config = {
                "disaster_recovery": {
                    "mode": mode,
                    "current_endpoint": (
                        replica_endpoint if mode == "replica" else primary_endpoint
                    ),
                    "endpoints": {
                        "primary": {
                            "endpoint": primary_endpoint,
                            "type": "primary",
                            "read_write": True,
                        },
                        "replica": {
                            "endpoint": replica_endpoint,
                            "type": "replica",
                            "read_write": False,
                        },
                    },
                    f"ailover_strategy": {
                        "auto_failover": False,
                        "health_check_interval": 30,
                        "timeout_threshold": 10,
                    },
                    "updated_at": "2025-06-07T00:00:00Z",
                }
            }

            with open(self.dr_config_file, "w") as f:
                json.dump(dr_config, f, indent=2)

            self.logger.info(
                f" Disaster recovery config created: {self.dr_config_file}"
            )
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to create DR config: {e}")
            return False

    def switch_to_replica(self, replica_endpoint: str) -> bool:
        """Switch application to use Neptune replica endpoint."""
        try:
            # Save current config first
            if not self.save_original_config():
                self.logger.warn(
                    "Could not save original config, continuing anyway...")

            # Parse endpoint
            if replica_endpoint.startswith("ws://"):
                # WebSocket format: ws://host:port/gremlin
                host_port = replica_endpoint.replace("ws://", "").replace(
                    "/gremlin", ""
                )
                if ":" in host_port:
                    host, port = host_port.split(":", 1)
                else:
                    host, port = host_port, "8182"
            else:
                # Host:port format
                if ":" in replica_endpoint:
                    host, port = replica_endpoint.split(":", 1)
                else:
                    host, port = replica_endpoint, "8182"

            # Set environment variables
            os.environ["NEPTUNE_HOST"] = host
            os.environ["NEPTUNE_PORT"] = port
            os.environ["NEPTUNE_ENDPOINT"] = f"ws://{host}:{port}/gremlin"

            # Update .env file if it exists
            self._update_env_file(
                {
                    "NEPTUNE_HOST": host,
                    "NEPTUNE_PORT": port,
                    "NEPTUNE_ENDPOINT": f"ws://{host}:{port}/gremlin",
                }
            )

            self.logger.info(f" Switched to replica endpoint: {host}:{port}")
            self.logger.info(
                "🔄 Application should be restarted to use new endpoint")

            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to switch to replica: {e}")
            return False

    def switch_to_primary(self) -> bool:
        """Switch back to primary Neptune endpoint."""
        try:
            if not self.original_config_file.exists():
                self.logger.error(
                    "Original configuration not found - cannot rollback")
                return False

            with open(self.original_config_file, "r") as f:
                original_config = json.load(f)

            # Restore environment variables
            if original_config.get("neptune_endpoint"):
                os.environ["NEPTUNE_ENDPOINT"] = original_config["neptune_endpoint"]

            if original_config.get("neptune_host"):
                os.environ["NEPTUNE_HOST"] = original_config["neptune_host"]

            if original_config.get("neptune_port"):
                os.environ["NEPTUNE_PORT"] = original_config["neptune_port"]

            # Update .env file
            env_updates = {}
            for key in ["NEPTUNE_ENDPOINT", "NEPTUNE_HOST", "NEPTUNE_PORT"]:
                if original_config.get(key.lower()):
                    env_updates[key] = original_config[key.lower()]

            self._update_env_file(env_updates)

            self.logger.info(" Switched back to primary endpoint")
            self.logger.info(
                "🔄 Application should be restarted to use primary endpoint"
            )

            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to switch to primary: {e}")
            return False

    def get_current_config(self) -> Dict[str, Any]:
        """Get current Neptune configuration."""
        return {
            "current_endpoint": os.getenv("NEPTUNE_ENDPOINT", "Not set"),
            "current_host": os.getenv("NEPTUNE_HOST", "Not set"),
            "current_port": os.getenv("NEPTUNE_PORT", "Not set"),
            "has_dr_config": self.dr_config_file.exists(),
            "has_original_backup": self.original_config_file.exists(),
        }

    def test_endpoint(self, endpoint: str) -> bool:
        """Test connectivity to a Neptune endpoint."""
        try:
            import asyncio

            from gremlin_python.driver.aiohttp.transport import \
                AiohttpTransport
            from gremlin_python.driver.client import Client

            async def test_connection():
                try:
                    client = Client(
                        endpoint, "g", transport_factory=lambda: AiohttpTransport()
                    )

                    # Simple connectivity test
                    result = await client.submit_async("g.V().limit(1).count()")
                    await result.all()
                    await client.close()
                    return True

                except Exception as e:
                    self.logger.debug(f"Connection test failed: {e}")
                    return False

            return asyncio.run(test_connection())

        except ImportError:
            self.logger.warn(
                "Gremlin dependencies not available for connection testing"
            )
            return False
        except Exception as e:
            self.logger.error(f"Connection test error: {e}")
            return False

    def _update_env_file(self, updates: Dict[str, str], env_file: str = ".env") -> bool:
        """Update .env file with new values."""
        try:
            env_vars = {}

            # Read existing .env file if it exists
            if os.path.exists(env_file):
                with open(env_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            env_vars[key] = value

            # Update with new values
            env_vars.update(updates)

            # Write updated .env file
            with open(env_file, "w") as f:
                f.write("# Neptune Configuration - Updated by Failover Manager"
")
                f.write("# Updated: 2025-06-07T00:00:00Z

")"
                for key, value in env_vars.items():
                    f.write(f"{key}={value}"
")"

            self.logger.info(f" Updated {env_file}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to update {env_file}: {e}")
            return False


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Neptune Failover Configuration Manager"
    )
    parser.add_argument(
        "action",
        choices=["switch-to-replica", "switch-to-primary", "status", "test"],
        help="Action to perform",
    )
    parser.add_argument(
        "--replica-endpoint", help="Replica endpoint (required for switch-to-replica)"
    )
    parser.add_argument(
        "--primary-endpoint", help="Primary endpoint (optional, for configuration)"
    )
    parser.add_argument("--test-endpoint", help="Endpoint to test connectivity")
    parser.add_argument(
        "--config-dir",
        default="config",
        help="Configuration directory (default: config)",
    )

    args = parser.parse_args()

    manager = NeptuneFailoverManager(config_dir=args.config_dir)

    if args.action == "switch-to-replica":
        if not args.replica_endpoint:
            print("❌ --replica-endpoint is required for switch-to-replica action")
            return 1

        print(f"🔄 Switching to replica endpoint: {args.replica_endpoint}")

        # Test endpoint first
        if manager.test_endpoint(args.replica_endpoint):
            print(" Replica endpoint connectivity test passed")
        else:
            print("⚠️  Replica endpoint connectivity test failed, proceeding anyway...")

        if manager.switch_to_replica(args.replica_endpoint):
            if args.primary_endpoint:
                manager.create_failover_config(
                    args.primary_endpoint, args.replica_endpoint, "replica"
                )
            print(" Successfully switched to replica endpoint")
            return 0
        else:
            print("❌ Failed to switch to replica endpoint")
            return 1

    elif args.action == "switch-to-primary":
        print("🔄 Switching back to primary endpoint")
        if manager.switch_to_primary():
            print(" Successfully switched to primary endpoint")
            return 0
        else:
            print("❌ Failed to switch to primary endpoint")
            return 1

    elif args.action == "status":
        config = manager.get_current_config()
        print(" Current Neptune Configuration:")
        for key, value in config.items():
            print(f"  {key}: {value}")
        return 0

    elif args.action == "test":
        endpoint = args.test_endpoint or os.getenv("NEPTUNE_ENDPOINT")
        if not endpoint:
            print(
                "❌ No endpoint to test (specify --test-endpoint or set NEPTUNE_ENDPOINT)"
            )
            return 1

        print(f" Testing connectivity to: {endpoint}")
        if manager.test_endpoint(endpoint):
            print(" Connection test passed")
            return 0
        else:
            print("❌ Connection test failed")
            return 1


if __name__ == "__main__":
    exit(main())
