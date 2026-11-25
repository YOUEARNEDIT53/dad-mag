#!/usr/bin/env python3
"""
Dad Mag — sync run state with a private Supabase Storage bucket.

The Render cron job starts on a blank disk every week, so the files that carry
over between editions live in the bucket:
  used_stories.json, used_topics.json   (no-repeat history)
  distro/subscribers.json               (audience; kept out of git)
  editions/*.md                         (archive + edition numbering)

Usage:
  python3 scripts/state_sync.py pull
  python3 scripts/state_sync.py push

Env: STATE_SUPABASE_URL, STATE_SUPABASE_KEY (service key), STATE_BUCKET (default dad-mag-state)
"""

import glob
import os
import sys

import requests

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILES = ['used_stories.json', 'used_topics.json', 'distro/subscribers.json']


def config():
    url = os.environ.get('STATE_SUPABASE_URL')
    key = os.environ.get('STATE_SUPABASE_KEY')
    if not url or not key:
        print("ERROR: STATE_SUPABASE_URL and STATE_SUPABASE_KEY must be set")
        sys.exit(1)
    bucket = os.environ.get('STATE_BUCKET', 'dad-mag-state')
    headers = {'Authorization': f'Bearer {key}', 'apikey': key}
    return f"{url}/storage/v1/object", bucket, headers


def list_remote(base, bucket, headers, prefix=''):
    r = requests.post(f"{base}/list/{bucket}", headers=headers, timeout=30,
                      json={'prefix': prefix, 'limit': 1000})
    r.raise_for_status()
    return [o['name'] for o in r.json() if o.get('id')]


def pull():
    base, bucket, headers = config()
    paths = list_remote(base, bucket, headers) + \
        [f"editions/{n}" for n in list_remote(base, bucket, headers, 'editions/')] + \
        [f"distro/{n}" for n in list_remote(base, bucket, headers, 'distro/')]
    for path in paths:
        r = requests.get(f"{base}/{bucket}/{path}", headers=headers, timeout=30)
        r.raise_for_status()
        local = os.path.join(PROJECT_DIR, path)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        with open(local, 'wb') as f:
            f.write(r.content)
    print(f"Pulled {len(paths)} state files")
    if not os.path.exists(os.path.join(PROJECT_DIR, 'distro/subscribers.json')):
        print("ERROR: distro/subscribers.json missing from bucket")
        sys.exit(1)


def push():
    base, bucket, headers = config()
    paths = [p for p in STATE_FILES if os.path.exists(os.path.join(PROJECT_DIR, p))]
    paths += [os.path.relpath(p, PROJECT_DIR) for p in glob.glob(os.path.join(PROJECT_DIR, 'editions', 'edition_*.md'))]
    for path in paths:
        with open(os.path.join(PROJECT_DIR, path), 'rb') as f:
            r = requests.post(f"{base}/{bucket}/{path}", data=f.read(), timeout=30,
                              headers={**headers, 'x-upsert': 'true', 'Content-Type': 'text/plain'})
        r.raise_for_status()
    print(f"Pushed {len(paths)} state files")


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ('pull', 'push'):
        print(__doc__)
        sys.exit(1)
    pull() if sys.argv[1] == 'pull' else push()
