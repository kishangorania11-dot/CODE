#!/usr/bin/env python3
"""Scan Adzuna for Amazon warehouse jobs within a radius of Leicester and
notify via Telegram about any postings not seen on a previous run."""

import json
import math
import os
import sys
from pathlib import Path

import requests

LEICESTER_LAT = 52.6369
LEICESTER_LON = -1.1398
MAX_DISTANCE_MILES = 40
SEARCH_TERMS = ["amazon warehouse", "amazon fulfilment", "amazon delivery"]
RESULTS_PER_PAGE = 50
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


def fetch_candidates():
    jobs_by_id = {}
    for term in SEARCH_TERMS:
        url = "https://api.adzuna.com/v1/api/jobs/gb/search/1"
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
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        for job in resp.json().get("results", []):
            jobs_by_id[job["id"]] = job
    return list(jobs_by_id.values())


def is_amazon_job(job):
    company = (job.get("company", {}) or {}).get("display_name", "") or ""
    title = job.get("title", "") or ""
    return "amazon" in company.lower() or "amazon" in title.lower()


def within_radius(job):
    lat = job.get("latitude")
    lon = job.get("longitude")
    if lat is None or lon is None:
        return False
    return haversine_miles(LEICESTER_LAT, LEICESTER_LON, lat, lon) <= MAX_DISTANCE_MILES


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


def format_job_message(job, distance_miles, label="New Amazon warehouse job near Leicester"):
    title = job.get("title", "Untitled role")
    location = (job.get("location", {}) or {}).get("display_name", "Unknown location")
    link = job.get("redirect_url", "")
    return (
        f"{label}\n\n"
        f"{title}\n"
        f"{location} (~{distance_miles:.0f} miles from Leicester)\n"
        f"{link}"
    )


def main():
    sample_size = int(os.environ.get("SAMPLE_SIZE", "0"))

    is_first_run = not SEEN_JOBS_PATH.exists()
    seen_ids = load_seen_ids()

    candidates = fetch_candidates()
    matching_jobs = [job for job in candidates if is_amazon_job(job) and within_radius(job)]

    if sample_size > 0:
        for job in matching_jobs[:sample_size]:
            lat, lon = job["latitude"], job["longitude"]
            distance = haversine_miles(LEICESTER_LAT, LEICESTER_LON, lat, lon)
            send_telegram_message(format_job_message(job, distance, label="Amazon warehouse job near Leicester"))
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

    all_current_ids = seen_ids | {str(job["id"]) for job in matching_jobs}
    save_seen_ids(all_current_ids)

    print(f"Checked {len(candidates)} candidates, {len(matching_jobs)} matched, {len(new_jobs)} new.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Scan failed: {exc}", file=sys.stderr)
        sys.exit(1)
