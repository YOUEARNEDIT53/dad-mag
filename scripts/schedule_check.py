#!/usr/bin/env python3
"""
Dad Mag — decide what today's cloud run should publish (US Eastern time).

Prints one line:
  holiday<TAB><theme>   tomorrow is a holiday: publish a themed special edition today
  sunday                regular Sunday edition
  skip                  nothing today

A Sunday edition is skipped when a special went out yesterday (eve of a Sunday holiday
like Easter or Father's Day) so readers don't get two editions in two days.

Usage: python3 scripts/schedule_check.py [--date YYYY-MM-DD]   # --date to preview a day
"""

import argparse
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAST_SPECIAL_PATH = os.path.join(PROJECT_DIR, 'last_special.json')


def nth_weekday(year, month, weekday, n):
    """n-th given weekday (Mon=0) of a month; n=-1 for the last one."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def easter(year):
    """Gregorian Easter Sunday (anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def holidays(year):
    return {
        date(year, 1, 1): "New Year's Day",
        easter(year): "Easter",
        nth_weekday(year, 5, 0, -1): "Memorial Day",
        nth_weekday(year, 6, 6, 3): "Father's Day",
        date(year, 7, 4): "Independence Day (Fourth of July)",
        nth_weekday(year, 9, 0, 1): "Labor Day",
        nth_weekday(year, 11, 3, 4): "Thanksgiving",
        date(year, 12, 25): "Christmas",
    }


def decide(today):
    tomorrow = today + timedelta(days=1)
    name = holidays(tomorrow.year).get(tomorrow)
    if name:
        theme = f"{name} (tomorrow, {tomorrow.strftime('%A %b')} {tomorrow.day}) and the holiday"
        return f"holiday\t{theme}"
    if today.weekday() == 6:
        if os.path.exists(LAST_SPECIAL_PATH):
            with open(LAST_SPECIAL_PATH) as f:
                last = date.fromisoformat(json.load(f)['date'])
            if (today - last).days <= 1:
                return "skip"
        return "sunday"
    return "skip"


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', help='preview a specific day (YYYY-MM-DD)')
    args = ap.parse_args()
    today = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo('America/New_York')).date()
    print(decide(today))
