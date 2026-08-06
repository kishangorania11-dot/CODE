#!/usr/bin/env python3
"""One-off discovery script: loads jobsatamazon.co.uk with a real browser
and logs any JSON API calls the page makes, plus a dump of visible job
links, so we can figure out how to query it programmatically. Not part
of the regular scan - run manually via the discover-jobsatamazon workflow."""

from playwright.sync_api import sync_playwright

URLS_TO_TRY = [
    "https://www.jobsatamazon.co.uk/",
    "https://www.jobsatamazon.co.uk/associate-roles/warehouse-operative",
    "https://www.jobsatamazon.co.uk/jobDetail/en-GB/Warehouse-Operative/Leicester-Area/JOB-UK-0000000109",
]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))

        captured = []

        def on_response(response):
            url = response.url
            content_type = response.headers.get("content-type", "")
            if "json" in content_type and response.request.resource_type in ("xhr", "fetch"):
                try:
                    body = response.text()
                except Exception as exc:
                    body = f"<error reading body: {exc}>"
                captured.append((response.request.method, url, body[:2000]))

        page.on("response", on_response)

        for url in URLS_TO_TRY:
            print(f"\n=== Navigating to {url} ===")
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception as exc:
                print(f"Navigation error: {exc}")
                continue
            print(f"Final URL: {page.url}")
            print(f"Page title: {page.title()}")

            links = page.eval_on_selector_all(
                "a[href*='jobDetail'], a[href*='job']",
                "els => els.slice(0, 20).map(e => e.href)",
            )
            print(f"Found {len(links)} job-like links (first 20):")
            for link in links:
                print(f"  {link}")

        print(f"\n=== Captured {len(captured)} JSON XHR/fetch responses ===")
        for method, url, body in captured:
            print(f"\n{method} {url}")
            print(body)

        browser.close()


if __name__ == "__main__":
    main()
