#!/usr/bin/env bash
# smtp-test: smoke-test the scheduled report email delivery path.
#
# Starts a local SMTP sink, creates a test subscription, fires the weekly
# delivery job, captures the email, and cleans up — no real SMTP server or
# API server required.
#
# Usage:
#   bash .claude/skills/smtp-test/smtp-test.sh [--to EMAIL] [--topic TOPIC] [--freq weekly|monthly] [--format pdf|csv]
#
# All args are forwarded to run_test.py. Defaults: --to test@noesis.local --topic AI --freq weekly --format pdf

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

exec python3 "$SCRIPT_DIR/run_test.py" "$@"
