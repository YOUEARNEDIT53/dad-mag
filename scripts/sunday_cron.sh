#!/bin/bash
# Dad Mag — Sunday Morning Automation
# Cron: 0 6 * * 0 /home/eng/dad-mag/scripts/sunday_cron.sh
#
# Full pipeline:
# 1. Scrape all 50 RSS feeds
# 2. Generate the Sunday Edition via Claude agents
# 3. Email it to subscribers (distro/subscribers.json)
# 4. Log results

set -euo pipefail

PROJECT_DIR="/home/eng/dad-mag"
VENV="$PROJECT_DIR/.venv/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"
TIMESTAMP=$(date +"%Y-%m-%d_%H%M%S")
LOG_FILE="$LOG_DIR/sunday_${TIMESTAMP}.log"

mkdir -p "$LOG_DIR"

echo "========================================" | tee -a "$LOG_FILE"
echo "DAD MAG SUNDAY SPRINT — $TIMESTAMP" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Step 1: Scrape feeds
echo "[1/2] Scraping RSS feeds..." | tee -a "$LOG_FILE"
$VENV "$PROJECT_DIR/newsroom_sync.py" >> "$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: Feed scrape failed. Check $LOG_FILE" | tee -a "$LOG_FILE"
    exit 1
fi

# Step 2: Generate edition (requires ANTHROPIC_API_KEY in environment)
echo "[2/2] Generating Sunday Edition..." | tee -a "$LOG_FILE"

# Source env file if it exists
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

$VENV "$PROJECT_DIR/workflow/generate_edition.py" >> "$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: Edition generation failed. Check $LOG_FILE" | tee -a "$LOG_FILE"
    exit 1
fi

echo "SUCCESS. Sunday Edition generated." | tee -a "$LOG_FILE"

# Step 3: Email the edition to subscribers
echo "[3/3] Sending edition..." | tee -a "$LOG_FILE"
if ! $VENV "$PROJECT_DIR/scripts/send_edition.py" >> "$LOG_FILE" 2>&1; then
    echo "ERROR: Send failed. Check $LOG_FILE" | tee -a "$LOG_FILE"
    exit 1
fi
echo "SENT." | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE" | tee -a "$LOG_FILE"

# Cleanup old logs (keep last 12)
ls -1t "$LOG_DIR"/sunday_*.log 2>/dev/null | tail -n +13 | xargs -r rm
