#!/usr/bin/env python3
"""
Dad Mag — Send Edition via Resend
Sends the latest edition to the distro list.

Usage:
  python3 send_edition.py                     # Send latest edition
  python3 send_edition.py --edition 001       # Send specific edition
  python3 send_edition.py --dry-run           # Preview without sending
"""

import json
import os
import sys
import glob
import argparse
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
EDITIONS_DIR = os.path.join(PROJECT_DIR, 'editions')
DISTRO_PATH = os.path.join(PROJECT_DIR, 'distro', 'subscribers.json')

import time

try:
    import resend
except ImportError:
    print("NOTE: resend package not installed. Run: pip install resend")
    resend = None

try:
    import requests
except ImportError:
    requests = None


def load_env():
    """Load environment variables, overridden by the .env file when present (local runs)."""
    env_path = os.path.join(PROJECT_DIR, '.env')
    env = dict(os.environ)
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def get_latest_edition():
    """Find the most recent edition file."""
    pattern = os.path.join(EDITIONS_DIR, 'edition_*.md')
    files = sorted(glob.glob(pattern))
    if not files:
        print("ERROR: No editions found in editions/")
        sys.exit(1)
    return files[-1]


def get_specific_edition(num):
    """Find a specific edition by number."""
    pattern = os.path.join(EDITIONS_DIR, f'edition_{int(num):03d}_*.md')
    files = glob.glob(pattern)
    if not files:
        print(f"ERROR: Edition #{num} not found")
        sys.exit(1)
    return files[0]


def markdown_to_html(md_text):
    """Convert markdown to basic HTML for email."""
    html = md_text

    # Headers
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

    # Bold and italic
    html = re.sub(r'\*\*\[(.+?)\]\*\*', r'<strong>[\1]</strong>', html)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

    # Horizontal rules
    html = html.replace('---', '<hr>')

    # Paragraphs
    paragraphs = html.split('\n\n')
    formatted = []
    for p in paragraphs:
        p = p.strip()
        if p and not p.startswith('<h') and not p.startswith('<hr'):
            p = f'<p>{p}</p>'
        formatted.append(p)
    html = '\n'.join(formatted)

    # Wrap in basic email template
    return f"""<!DOCTYPE html>
<html>
<head>
<style>
body {{ font-family: Georgia, serif; max-width: 680px; margin: 0 auto; padding: 20px; color: #1a1a1a; line-height: 1.6; }}
h1 {{ font-size: 28px; border-bottom: 3px solid #333; padding-bottom: 10px; }}
h2 {{ font-size: 22px; color: #333; margin-top: 30px; }}
h3 {{ font-size: 18px; color: #555; }}
strong {{ color: #222; }}
hr {{ border: none; border-top: 1px solid #ddd; margin: 25px 0; }}
p {{ margin: 12px 0; }}
em {{ color: #666; }}
</style>
</head>
<body>
{html}
</body>
</html>"""


def local_subscribers():
    """Active subscribers from distro/subscribers.json (primary + subscribers list)."""
    with open(DISTRO_PATH) as f:
        distro = json.load(f)
    subs = [distro['primary']] + distro.get('subscribers', [])
    return [{'email': s['email'], 'name': s.get('name', '')}
            for s in subs if s.get('status', 'active') == 'active']


def fetch_subscribers(env):
    """Pull active subscribers from Supabase, falling back to the local distro list."""
    supabase_url = env.get('SUPABASE_URL')
    supabase_key = env.get('SUPABASE_SERVICE_KEY')

    if not supabase_url or not supabase_key or not requests:
        return local_subscribers()

    url = f"{supabase_url}/rest/v1/subscribers?status=eq.active&select=email,name"
    headers = {
        'apikey': supabase_key,
        'Authorization': f'Bearer {supabase_key}'
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        subs = r.json()
    except Exception as e:
        print(f"  Supabase subscriber fetch failed ({type(e).__name__}); using local distro list")
        return local_subscribers()

    if not subs:
        return local_subscribers()

    return subs


def send_email(edition_path, dry_run=False):
    """Send the edition to all active subscribers via Resend."""
    env = load_env()

    with open(edition_path) as f:
        content = f.read()

    # Extract title from first line
    title_match = re.match(r'# (.+)', content)
    subject = title_match.group(1) if title_match else "Dad Mag: Sunday Edition"

    html = markdown_to_html(content)
    from_email = env.get('DIGEST_EMAIL_FROM', 'Dad Mag <onboarding@resend.dev>')

    # Fetch full distro list from Supabase
    subscribers = fetch_subscribers(env)

    print(f"Edition: {os.path.basename(edition_path)}")
    print(f"Subject: {subject}")
    print(f"From: {from_email}")
    print(f"Content: {len(content)} chars markdown, {len(html)} chars HTML")
    print(f"Recipients: {len(subscribers)}")
    for s in subscribers:
        print(f"  - {s['email']} ({s.get('name', '')})")

    if dry_run:
        print("\n[DRY RUN] Emails not sent.")
        preview_path = os.path.join(PROJECT_DIR, 'editions', 'preview.html')
        with open(preview_path, 'w') as f:
            f.write(html)
        print(f"  HTML preview saved: {preview_path}")
        return

    if not resend:
        print("ERROR: resend package not installed")
        sys.exit(1)

    api_key = env.get('RESEND_API_KEY')
    if not api_key:
        print("ERROR: RESEND_API_KEY not found")
        sys.exit(1)

    resend.api_key = api_key

    sent = 0
    failed = 0
    for sub in subscribers:
        try:
            params = {
                "from": from_email,
                "to": [sub['email']],
                "subject": subject,
                "html": html,
                "text": content,
            }
            result = resend.Emails.send(params)
            print(f"  Sent to {sub['email']} — ID: {result.get('id', 'ok')}")
            sent += 1
            time.sleep(0.2)  # Rate limit courtesy
        except Exception as e:
            print(f"  FAILED {sub['email']}: {e}")
            failed += 1

    print(f"\nDone. Sent: {sent}, Failed: {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dad Mag Email Sender")
    parser.add_argument('--edition', type=int, help='Edition number to send')
    parser.add_argument('--dry-run', action='store_true', help='Preview without sending')
    args = parser.parse_args()

    if args.edition:
        path = get_specific_edition(args.edition)
    else:
        path = get_latest_edition()

    send_email(path, dry_run=args.dry_run)
