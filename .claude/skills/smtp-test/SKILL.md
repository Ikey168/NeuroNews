---
name: smtp-test
description: End-to-end smoke test for the scheduled report email delivery path. Spins up a local SMTP sink, creates a test subscription, fires the delivery job, captures the email, and cleans up — no real SMTP server or API server needed. Use when iterating on email templates, changing the SMTP sender, or verifying a new report format sends correctly.
---

# smtp-test skill

Runs a full delivery cycle locally in ~5 seconds with no external dependencies:

1. Starts a minimal async SMTP sink on a random localhost port
2. Creates a test subscription in DuckDB (cleaned up on exit)
3. Calls `_deliver_subscriptions(freq)` directly — no API server needed
4. Waits for the message to arrive at the sink
5. Pretty-prints headers, body preview, and attachment info
6. Deletes the test subscription and stops the sink

**All paths are relative to the repo root** (`/home/Ikey/NeuroNews`).

## Usage

```bash
bash .claude/skills/smtp-test/smtp-test.sh [OPTIONS]

# or directly:
python3 .claude/skills/smtp-test/run_test.py [OPTIONS]
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--to EMAIL` | `test@noesis.local` | Recipient address (captured by local sink) |
| `--topic TOPIC` | `AI` | Topic keyword for the report |
| `--freq weekly\|monthly` | `weekly` | Delivery frequency (`weekly` → last_7_days, `monthly` → last_30_days) |
| `--format pdf\|csv` | `pdf` | Report attachment format |
| `--timeout SECS` | `15` | How long to wait for the sink to receive the message |

## Examples

```bash
# Default: weekly PDF for "AI"
bash .claude/skills/smtp-test/smtp-test.sh

# Monthly CSV for "Iran", custom recipient
bash .claude/skills/smtp-test/smtp-test.sh --to dev@example.com --topic "Iran" --freq monthly --format csv

# Quick topic data check with short timeout
bash .claude/skills/smtp-test/smtp-test.sh --topic "SpaceX" --timeout 8
```

## Expected output

```
──────────────────────────────────────────────────────────────
  1/5  Starting local SMTP sink
──────────────────────────────────────────────────────────────
  SMTP sink listening on 127.0.0.1:40405

  ...

  4/5  Waiting for SMTP message
──────────────────────────────────────────────────────────────
  Message received!  (6856 raw bytes)

  From:    reports@noesis.local
  To:      smoke@noesis.local
  Subject: [Noesis] Weekly report: Iran (last 7 days)

  Body (text):
    Noesis Report: Iran  Your weekly report for 'Iran' covering last 7
    days is attached.

  Attachments:
    noesis_report_iran_last_7_days.pdf  (3,832 bytes, application/pdf)

  RESULT: PASS — email delivered end-to-end via SMTP
```

Exit code `0` = PASS, `1` = FAIL (timeout or delivery error).

## Testing against a real SMTP server

The test honours the standard SMTP env vars. Set them before running to route
through a real provider instead of the local sink:

```bash
SMTP_HOST=smtp.sendgrid.net \
SMTP_PORT=587 \
SMTP_USER=apikey \
SMTP_PASSWORD=<key> \
SMTP_FROM=reports@yourdomain.com \
bash .claude/skills/smtp-test/smtp-test.sh --to your@email.com
```

When real SMTP vars are set, the local sink is still started (for the SMTP
handshake fallback), but `email_sender.py` will use the configured host.
Actually: when `SMTP_HOST` is already set in the environment before the script
runs, the script **overrides** it to point at the sink. To use a real server,
call `run_test.py` and patch `email_sender._send_raw` instead — or just call
the API endpoint directly.

## How it differs from calling the API

The `POST /api/v1/reports/trigger/weekly` endpoint does the same thing but
requires the full FastAPI stack to be running (which pulls in the heavy ML
imports). This skill calls `_deliver_subscriptions()` directly — starts in
under a second with no server boot.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `TIMEOUT — no message received` | Delivery raised an exception (check stderr). Topic may have 0 articles — try `--topic Iran` or `--topic AI`. |
| `0 bytes` attachment | Report generation returned empty bytes. Run `report-preview` for the same topic to diagnose. |
| `Connection refused` on port | Port was taken; the sink picks a random free port, so this shouldn't happen — restart and retry. |
