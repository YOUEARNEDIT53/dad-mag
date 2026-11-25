#!/bin/bash
# Dad Mag — Render Cron Job runner (see Dockerfile). Runs daily at 6 AM ET.
# With no args it asks scripts/schedule_check.py what today is:
#   day before a holiday -> themed special edition; Sunday -> regular edition; else exit.
# 1. Pull state (history, subscribers, past editions) from Supabase Storage
# 2. Scrape feeds  3. Generate the edition  4. Email it  5. Push state back
#
# Any args skip the calendar check and go to generate_edition.py (e.g. --theme "Christmas").
# TEST_EMAIL=you@x.com sends only to that address and does NOT save state.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
echo "===== $(date -Is) Dad Mag run start ====="

python scripts/state_sync.py pull

SPECIAL=""
if [ $# -eq 0 ]; then
    DECISION=$(python scripts/schedule_check.py)
    echo "--- schedule: $DECISION"
    case "$DECISION" in
        skip) echo "Nothing to publish today."; exit 0 ;;
        holiday*) SPECIAL=1; set -- --theme "$(printf '%s' "$DECISION" | cut -f2)" ;;
    esac
fi

echo "--- scrape feeds"
python newsroom_sync.py || echo "WARNING: some feeds failed; continuing with what loaded"

echo "--- generate edition"
python workflow/generate_edition.py "$@"

echo "--- send"
if [ -n "${TEST_EMAIL:-}" ]; then
    python - <<EOF
import json
p = 'distro/subscribers.json'
d = json.load(open(p))
d['primary'] = {'email': '$TEST_EMAIL', 'name': 'Test', 'status': 'active'}
d['subscribers'] = []
json.dump(d, open(p, 'w'))
EOF
    python scripts/send_edition.py
    echo "TEST MODE: state not saved"
else
    python scripts/send_edition.py
    if [ -n "$SPECIAL" ]; then
        python -c "import json, datetime, zoneinfo; json.dump({'date': datetime.datetime.now(zoneinfo.ZoneInfo('America/New_York')).date().isoformat()}, open('last_special.json', 'w'))"
    fi
    python scripts/state_sync.py push
fi
echo "===== $(date -Is) Dad Mag run end ====="
