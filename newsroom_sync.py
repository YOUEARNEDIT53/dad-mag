#!/usr/bin/env python3
"""
Dad Mag Newsroom Sync — RSS Feed Scraper
Parses sources.opml, grabs latest entries, outputs weekly_digest.json.
This is the "source of truth" that agents fight over.
"""

import feedparser
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import sys
import os
import hashlib
import time
import socket

# Reduce timeout for unresponsive feeds
socket.setdefaulttimeout(10)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OPML_PATH = os.path.join(SCRIPT_DIR, 'sources.opml')
DIGEST_PATH = os.path.join(SCRIPT_DIR, 'weekly_digest.json')
MAX_AGE_DAYS = 7
ENTRIES_PER_FEED = 3


def load_sources(opml_path):
    """Parse OPML file and extract all feed URLs with metadata."""
    tree = ET.parse(opml_path)
    root = tree.getroot()
    sources = []
    for outline in root.findall(".//outline[@xmlUrl]"):
        sources.append({
            'name': outline.get('text', 'Unknown'),
            'url': outline.get('xmlUrl'),
            'category': outline.get('category', 'general')
        })
    return sources


def is_recent(entry, max_age_days=MAX_AGE_DAYS):
    """Check if an entry was published within the last N days."""
    published = entry.get('published_parsed') or entry.get('updated_parsed')
    if not published:
        return True  # If no date, include it (benefit of the doubt)
    try:
        pub_date = datetime(*published[:6])
        cutoff = datetime.now() - timedelta(days=max_age_days)
        return pub_date >= cutoff
    except (ValueError, TypeError):
        return True


def hash_url(url):
    """Generate a short hash for deduplication."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


# Keywords for per-story categorization (overrides source-level category)
CATEGORY_KEYWORDS = {
    'clinical': [
        'study', 'research', 'trial', 'clinical', 'meta-analysis', 'rct',
        'randomized', 'placebo', 'cohort', 'lancet', 'nejm', 'pubmed',
        'evidence', 'mortality', 'morbidity', 'disease', 'cancer', 'heart',
        'cardiovascular', 'diabetes', 'hypertension', 'cholesterol', 'blood',
        'biomarker', 'inflammation', 'cortisol', 'testosterone', 'hormone',
        'vaccine', 'therapy', 'treatment', 'diagnosis', 'pathology', 'patient',
        'physician', 'orthopedic', 'injury', 'rehab', 'physical therapy',
        'surgery', 'bone', 'joint', 'tendon', 'ligament', 'fracture', 'pain',
        'chronic', 'acute', 'dose', 'mechanism', 'receptor', 'cell',
    ],
    'performance': [
        'strength', 'hypertrophy', 'powerlifting', 'deadlift', 'squat', 'bench',
        'press', 'barbell', 'dumbbell', 'kettlebell', 'rep', 'set', 'volume',
        'intensity', 'progressive overload', 'periodization', 'training',
        'workout', 'exercise', 'muscle', 'gains', 'recovery', 'protein',
        'creatine', 'whey', 'amino', 'endurance', 'cardio', 'hiit', 'vo2',
        'sprint', 'running', 'marathon', 'conditioning', 'mobility', 'stretch',
        'warm-up', 'cooldown', 'athlete', 'coach', 'programming', 'deload',
        'pr', 'one-rep', 'compound', 'isolation', 'bodyweight', 'calisthenics',
    ],
    'biohack': [
        'wearable', 'tracker', 'garmin', 'whoop', 'oura', 'apple watch',
        'hrv', 'heart rate', 'sleep', 'circadian', 'melatonin', 'cold plunge',
        'sauna', 'red light', 'infrared', 'peptide', 'nootropic', 'longevity',
        'rapamycin', 'nad', 'nmn', 'resveratrol', 'fasting', 'autophagy',
        'ketosis', 'glucose', 'cgm', 'continuous glucose', 'biohack',
        'optimization', 'protocol', 'stack', 'supplement', 'hack', 'attia',
        'huberman', 'zone 2', 'mitochondria', 'telomere', 'epigenetic',
        'blood work', 'lab test', 'bioage', 'healthspan', 'lifespan',
    ],
    'trends': [
        'trend', 'viral', 'tiktok', 'instagram', 'influencer', 'brand',
        'wellness', 'lifestyle', 'aesthetic', 'clean', 'organic', 'natural',
        'gut health', 'probiotic', 'greens powder', 'smoothie', 'recipe',
        'meal prep', 'diet', 'keto', 'paleo', 'mediterranean', 'carnivore',
        'vegan', 'plant-based', 'mindfulness', 'meditation', 'yoga',
        'breathwork', 'mental health', 'anxiety', 'stress', 'burnout',
        'self-care', 'therapy', 'journaling', 'gratitude', 'dopamine',
        'serotonin', 'psychology', 'motivation', 'discipline', 'habit',
        'product', 'subscription', 'goop', 'well+good', 'packaging',
    ],
}


def classify_story(title, summary, source_category):
    """Classify a story by scanning title + summary for category keywords."""
    text = (title + ' ' + summary).lower()
    scores = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        scores[cat] = sum(1 for kw in keywords if kw in text)

    best_cat = max(scores, key=scores.get)
    # Only override if we got meaningful signal (2+ keyword hits)
    if scores[best_cat] >= 2:
        return best_cat
    return source_category


def scrape_feeds(sources):
    """Hit every feed. Grab top entries. Return structured digest."""
    digest = []
    seen_urls = set()
    errors = []

    total = len(sources)
    for i, source in enumerate(sources, 1):
        print(f"[{i}/{total}] Scanning: {source['name']}...", end=" ", flush=True)
        try:
            feed = feedparser.parse(source['url'])

            if feed.bozo and not feed.entries:
                print("FAIL (bad feed)")
                errors.append({'source': source['name'], 'error': str(feed.bozo_exception)})
                continue

            count = 0
            for entry in feed.entries[:ENTRIES_PER_FEED * 2]:  # Grab extra, filter by date
                if count >= ENTRIES_PER_FEED:
                    break

                if not is_recent(entry):
                    continue

                link = entry.get('link', '')
                url_hash = hash_url(link)
                if url_hash in seen_urls:
                    continue
                seen_urls.add(url_hash)

                # Extract publish date
                pub_parsed = entry.get('published_parsed') or entry.get('updated_parsed')
                if pub_parsed:
                    pub_date = datetime(*pub_parsed[:6]).strftime("%Y-%m-%d")
                else:
                    pub_date = datetime.now().strftime("%Y-%m-%d")

                # Clean summary (strip HTML tags roughly)
                summary = entry.get('summary', '')
                if '<' in summary:
                    import re
                    summary = re.sub(r'<[^>]+>', '', summary)
                summary = summary[:500]  # Cap length

                title = entry.get('title', 'Untitled')
                story_category = classify_story(title, summary, source['category'])

                digest.append({
                    'id': url_hash,
                    'source': source['name'],
                    'category': story_category,
                    'title': title,
                    'link': link,
                    'summary': summary,
                    'date': pub_date
                })
                count += 1

            print(f"OK ({count} stories)")

        except Exception as e:
            print(f"ERROR ({e})")
            errors.append({'source': source['name'], 'error': str(e)})

        # Small delay to be polite
        time.sleep(0.3)

    return digest, errors


def rank_stories(digest):
    """Sort stories: most recent first, then by category diversity."""
    digest.sort(key=lambda x: x['date'], reverse=True)
    return digest


def generate_theme_suggestions(digest):
    """Extract potential cover story themes from title frequency."""
    from collections import Counter

    # Simple keyword extraction from titles
    stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'to', 'of', 'in',
                  'for', 'on', 'with', 'at', 'by', 'from', 'and', 'or', 'but', 'not',
                  'how', 'why', 'what', 'new', 'can', 'will', 'has', 'its', 'it', 'as',
                  'that', 'this', 'be', 'have', 'do', 'say', 'get', 'make', 'go', 'up',
                  'no', 'just', 'than', 'about', 'into', 'could', 'after', 'over', 'also'}

    words = Counter()
    for item in digest:
        title_words = item['title'].lower().split()
        for word in title_words:
            cleaned = word.strip('.,;:!?()[]"\'')
            if len(cleaned) > 3 and cleaned not in stop_words:
                words[cleaned] += 1

    # Top trending keywords
    trending = words.most_common(15)
    return [{'keyword': w, 'frequency': c} for w, c in trending]


if __name__ == "__main__":
    print("=" * 60)
    print("DAD MAG NEWSROOM SYNC")
    print(f"Scraping feeds from: {OPML_PATH}")
    print(f"Output: {DIGEST_PATH}")
    print(f"Max age: {MAX_AGE_DAYS} days")
    print("=" * 60)
    print()

    # 1. Load sources
    sources = load_sources(OPML_PATH)
    print(f"Loaded {len(sources)} sources from OPML\n")

    # 2. Scrape all feeds
    raw_digest, errors = scrape_feeds(sources)

    # 3. Rank and sort
    ranked = rank_stories(raw_digest)

    # 4. Extract themes
    themes = generate_theme_suggestions(ranked)

    # 5. Build output
    output = {
        'metadata': {
            'scraped_at': datetime.now().isoformat(),
            'sources_attempted': len(sources),
            'sources_with_errors': len(errors),
            'stories_collected': len(ranked),
            'max_age_days': MAX_AGE_DAYS
        },
        'trending_themes': themes,
        'stories': ranked,
        'errors': errors
    }

    # 6. Save
    with open(DIGEST_PATH, 'w') as f:
        json.dump(output, f, indent=2)

    print()
    print("=" * 60)
    print(f"DONE. {len(ranked)} stories loaded into weekly_digest.json")
    print(f"Errors: {len(errors)} feeds failed")
    print(f"Top themes: {', '.join(t['keyword'] for t in themes[:5])}")
    print("=" * 60)
