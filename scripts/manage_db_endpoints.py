#!/usr/bin/env python3

"""
Database Endpoint Manager for Disaster Recovery
This script helps switch between primary and backup database endpoints
"""

import argparse
import json
import os
from typing import Any, Dict, Optional

import boto3


class DatabaseEndpointManager:
    """Manages database endpoint configuration for disaster recovery."""

    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.redshift_client = boto3.client("redshift", region_name=region)
        self.neptune_client = boto3.client("neptune", region_name=region)

    def get_redshift_endpoint(self, cluster_identifier: str) -> Optional[str]:
        """Get Redshift cluster endpoint."""
        try:
            response = self.redshift_client.describe_clusters(
                ClusterIdentifier=cluster_identifier
            )
            cluster = response["Clusters"][0]
            return f"{cluster['Endpoint']['Address']}:{cluster['Endpoint']['Port']}"
        except Exception as e:
            print(f"Error getting Redshift endpoint: {e}")
            return None

    def get_neptune_endpoint(
        self, cluster_identifier: str, is_replica: bool = False
    ) -> Optional[str]:
        """Get Neptune cluster endpoint."""
        try:
            response = self.neptune_client.describe_db_clusters(
                DBClusterIdentifier=cluster_identifier
            )
            cluster = response["DBClusters"][0]

            if is_replica and cluster["ReadReplicaIdentifiers"]:
                # Get replica endpoint
                replica_response = self.neptune_client.describe_db_instances(
                    DBInstanceIdentifier=cluster["ReadReplicaIdentifiers"][0]
                )
                instance = replica_response["DBInstances"][0]
                return (
                    f"{instance['Endpoint']['Address']}:{instance['Endpoint']['Port']}"
                )
            else:
                # Get primary endpoint
                return f"{cluster['Endpoint']}:{cluster['Port']}"
        except Exception as e:
            print(f"Error getting Neptune endpoint: {e}")
            return None

    def update_environment_config(
        self,
        redshift_host: Optional[str] = None,
        neptune_host: Optional[str] = None,
        config_file: str = ".env",
    ) -> bool:
        """Update environment configuration file."""
        try:
            env_vars = {}

            # Read existing .env file if it exists
            if os.path.exists(config_file):
                with open(config_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            env_vars[key] = value

            # Update with new values
            if redshift_host:
                env_vars["REDSHIFT_HOST"] = redshift_host.split(":")[0]
                env_vars["REDSHIFT_PORT"] = (
                    redshift_host.split(
                        ":")[1] if ":" in redshift_host else "5439"
                )

            if neptune_host:
                env_vars["NEPTUNE_HOST"] = neptune_host.split(":")[0]
                env_vars["NEPTUNE_PORT"] = (
                    neptune_host.split(
                        ":")[1] if ":" in neptune_host else "8182"
                )

            # Write updated .env file
            with open(config_file, "w") as f:
                for key, value in env_vars.items():
                    f.write(f"{key}={value}"
")"

            print(f" Updated {config_file}")
            return True

        except Exception as e:
            print(f"❌ Error updating config: {e}")
            return False


    def create_app_config(
        self,
        redshift_endpoint: str,
        neptune_endpoint: str,
        config_file: str="config/disaster_recovery.json",
    ) -> bool:
        """Create application configuration for disaster recovery."""
        try:
            config={
                "disaster_recovery": {
                    "mode": "active",
                    "databases": {
                        "redshift": {
                            "endpoint": redshift_endpoint,
                            "type": (
                                "backup"
                                if "dr-test" in redshift_endpoint
                                else "primary"
                            ),
                        },
                        "neptune": {
                            "endpoint": neptune_endpoint,
                            "type": (
                                "replica"
                                if "replica" in neptune_endpoint
                                else "primary"
                            ),
                        },
                    },
                    "updated_at": "2025-06-07T00:00:00Z",
                }
            }

            os.makedirs(os.path.dirname(config_file), exist_ok=True)

            with open(config_file, "w") as f:
                json.dump(config, f, indent=2)

            print(f" Created disaster recovery config: {config_file}")
            return True

        except Exception as e:
            print(f"❌ Error creating config: {e}")
            return False


def main():
    parser=argparse.ArgumentParser(
        description="Manage database endpoints for disaster recovery"
    )
    parser.add_argument("--redshift-cluster", help="Redshift cluster identifier")
    parser.add_argument("--neptune-cluster", help="Neptune cluster identifier")
    parser.add_argument(
        "--use-replica", action="store_true", help="Use Neptune replica endpoint"
    )
    parser.add_argument(
        "--config-file",
        default=".env",
        help="Configuration file to update (default: .env)",
    )
    parser.add_argument(
        "--region", default="us-east-1", help="AWS region (default: us-east-1)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )

    args=parser.parse_args()

    manager=DatabaseEndpointManager(region=args.region)

    redshift_endpoint=None
    neptune_endpoint=None

    # Get Redshift endpoint
    if args.redshift_cluster:
        redshift_endpoint=manager.get_redshift_endpoint(args.redshift_cluster)
        if redshift_endpoint:
            print(f"📍 Redshift endpoint: {redshift_endpoint}")
        else:
            print(f"❌ Could not get Redshift endpoint for {args.redshift_cluster}")

    # Get Neptune endpoint
    if args.neptune_cluster:
        neptune_endpoint=manager.get_neptune_endpoint(
            args.neptune_cluster, is_replica=args.use_replica
        )
        if neptune_endpoint:
            endpoint_type="replica" if args.use_replica else "primary"
            print(f"📍 Neptune {endpoint_type} endpoint: {neptune_endpoint}")
        else:
            print(f"❌ Could not get Neptune endpoint for {args.neptune_cluster}")

    if args.dry_run:
        print(""
 DRY RUN - No changes will be made")"
        if redshift_endpoint:
            print(f"Would update REDSHIFT_HOST to: {redshift_endpoint}")
        if neptune_endpoint:
            print(f"Would update NEPTUNE_HOST to: {neptune_endpoint}")
        return

    # Update configuration
    if redshift_endpoint or neptune_endpoint:
        success=manager.update_environment_config(
            redshift_host=redshift_endpoint,
            neptune_host=neptune_endpoint,
            config_file=args.config_file,
        )

        if success and redshift_endpoint and neptune_endpoint:
            # Create disaster recovery config
            manager.create_app_config(redshift_endpoint, neptune_endpoint)

    print(""
 Database endpoint management completed")"


if __name__ == "__main__":
    main()
