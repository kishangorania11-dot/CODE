#!/usr/bin/env python3
"""Scan Adzuna for Amazon warehouse-tier jobs (Warehouse Operative,
Delivery Station Warehouse Associate, Sortation Operative, Amazon Fresh
Warehouse Team Member, Stower, Problem Solver, Dock Associate - see
TARGET_ROLE_KEYWORDS) within a radius of Leicester paying at least
MIN_HOURLY_RATE, and notify via Telegram about any postings not seen on a
previous run. Also sends a status message when a run finds nothing new.
Jobs with no listed salary are still included (can't verify their rate
either way) but flagged in the message."""

import json
import math
import os
import sys
from pathlib import Path

import requests

LEICESTER_LAT = 52.6369
LEICESTER_LON = -1.1398
MAX_DISTANCE_MILES = 60
MIN_HOURLY_RATE = 12.30
ASSUMED_ANNUAL_HOURS = 37.5 * 52  # full-time equivalent, used to interpret Adzuna's annualized salary_min
MIN_ANNUAL_SALARY = MIN_HOURLY_RATE * ASSUMED_ANNUAL_HOURS
SEARCH_TERMS = ["amazon"]
RESULTS_PER_PAGE = 50
MAX_PAGES = 4
SEEN_JOBS_PATH = Path(__file__).resolve().parent.parent / "data" / "seen_jobs.json"

ADZUNA_APP_ID = os.environ["ADZUNA_APP_ID"]
ADZUNA_APP_KEY = os.environ["ADZUNA_APP_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def haversine_miles(lat1, lon1, lat2, lon2):
    r_miles = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * r_miles * math.asin(math.sqrt(a))


def fetch_candidates(max_days_old=None):
    jobs_by_id = {}
    for term in SEARCH_TERMS:
        for page in range(1, MAX_PAGES + 1):
            url = f"https://api.adzuna.com/v1/api/jobs/gb/search/{page}"
            params = {
                "app_id": ADZUNA_APP_ID,
                "app_key": ADZUNA_APP_KEY,
                "what": term,
                "where": "Leicester",
                "distance": 80,
                "results_per_page": RESULTS_PER_PAGE,
                "sort_by": "date",
                "content-type": "application/json",
            }
            if max_days_old:
                params["max_days_old"] = max_days_old
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                break
            for job in results:
                jobs_by_id[job["id"]] = job
    return list(jobs_by_id.values())


TARGET_ROLE_KEYWORDS = [
    ("warehouse", "operative"),  # Warehouse Operative
    ("delivery station", "warehouse", "associate"),  # (Amazon) Delivery Station Warehouse Associate
    ("sortation", "operative"),  # Sortation Operative
    ("warehouse", "team member"),  # Amazon Fresh Warehouse Team Member
    ("stower",),  # Stower
    ("problem solver",),  # Problem Solver
    ("dock associate",),  # Dock Associate
]


def is_target_amazon_job(job):
    company = (job.get("company", {}) or {}).get("display_name", "") or ""
    title = (job.get("title", "") or "").lower()
    is_amazon = "amazon" in company.lower() or "amazon" in title
    matches_target_role = any(
        all(keyword in title for keyword in keywords) for keywords in TARGET_ROLE_KEYWORDS
    )
    return is_amazon and matches_target_role


def within_radius(job):
    lat = job.get("latitude")
    lon = job.get("longitude")
    if lat is None or lon is None:
        return False
    return haversine_miles(LEICESTER_LAT, LEICESTER_LON, lat, lon) <= MAX_DISTANCE_MILES


def meets_min_salary(job):
    """True if salary data is missing (can't verify, so don't exclude) or
    the listed salary implies at least MIN_HOURLY_RATE per hour."""
    salary_min = job.get("salary_min")
    if not salary_min:
        return True
    return salary_min >= MIN_ANNUAL_SALARY


def implied_hourly_rate(job):
    salary_min = job.get("salary_min")
    if not salary_min:
        return None
    return salary_min / ASSUMED_ANNUAL_HOURS


def load_seen_ids():
    if SEEN_JOBS_PATH.exists():
        return set(json.loads(SEEN_JOBS_PATH.read_text()))
    return set()


def save_seen_ids(ids):
    SEEN_JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_JOBS_PATH.write_text(json.dumps(sorted(ids), indent=2) + "\n")


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": "true"},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram API error: {body}")


def format_job_message(job, distance_miles, label="New Amazon job near Leicester"):
    title = job.get("title", "Untitled role")
    location = (job.get("location", {}) or {}).get("display_name", "Unknown location")
    link = job.get("redirect_url", "")
    hourly = implied_hourly_rate(job)
    pay_line = f"~£{hourly:.2f}/hr (estimated from listing)" if hourly else "Pay not listed — verify on application page"
    return (
        f"{label}\n\n"
        f"{title}\n"
        f"{location} (~{distance_miles:.0f} miles from Leicester)\n"
        f"{pay_line}\n"
        f"{link}"
    )


def main():
    sample_size = int(os.environ.get("SAMPLE_SIZE", "0"))
    max_days_old = os.environ.get("MAX_DAYS_OLD") or None

    is_first_run = not SEEN_JOBS_PATH.exists()
    seen_ids = load_seen_ids()

    candidates = fetch_candidates(max_days_old=max_days_old)

    if sample_size > 0:
        print(f"DEBUG: fetched {len(candidates)} raw candidates before any filtering.")
        for job in candidates[:30]:
            company = (job.get("company", {}) or {}).get("display_name", "")
            loc = (job.get("location", {}) or {}).get("display_name", "")
            lat, lon = job.get("latitude"), job.get("longitude")
            dist = haversine_miles(LEICESTER_LAT, LEICESTER_LON, lat, lon) if lat and lon else None
            dist_str = f"{dist:.0f}mi" if dist is not None else "no coords"
            print(f"DEBUG: [{company}] {job.get('title')} - {loc} ({dist_str})")

    matching_jobs = [
        job
        for job in candidates
        if is_target_amazon_job(job) and within_radius(job) and meets_min_salary(job)
    ]

    if sample_size > 0:
        if not matching_jobs:
            send_telegram_message(
                "No Amazon warehouse-tier jobs found within 60 miles of Leicester "
                + (f"in the last {max_days_old} days." if max_days_old else "right now.")
            )
            print("No matching jobs to send as sample.")
        for job in matching_jobs[:sample_size]:
            lat, lon = job["latitude"], job["longitude"]
            distance = haversine_miles(LEICESTER_LAT, LEICESTER_LON, lat, lon)
            send_telegram_message(format_job_message(job, distance, label="Amazon job near Leicester"))
            print(f"Sent sample: {job.get('title')} ({job['id']})")
        print(f"Sent {min(sample_size, len(matching_jobs))} sample jobs, no state changes made.")
        return

    if is_first_run:
        new_jobs = []
        print("First run: establishing baseline without sending notifications.")
    else:
        new_jobs = [job for job in matching_jobs if str(job["id"]) not in seen_ids]

    for job in new_jobs:
        lat, lon = job["latitude"], job["longitude"]
        distance = haversine_miles(LEICESTER_LAT, LEICESTER_LON, lat, lon)
        send_telegram_message(format_job_message(job, distance))
        print(f"Notified: {job.get('title')} ({job['id']})")

    if not is_first_run and not new_jobs:
        send_telegram_message(
            "No new Amazon warehouse-tier jobs within 60 miles of Leicester this hour."
        )
        print("No new jobs this run, sent status message.")

    all_current_ids = seen_ids | {str(job["id"]) for job in matching_jobs}
    save_seen_ids(all_current_ids)

    print(f"Checked {len(candidates)} candidates, {len(matching_jobs)} matched, {len(new_jobs)} new.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Scan failed: {exc}", file=sys.stderr)
        sys.exit(1)
