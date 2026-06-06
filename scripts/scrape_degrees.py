"""Scrape Marwadi University programs into data/degrees.json (key-value format).

NOTE: Public aggregator pages change their HTML often and the official site
gates some data. This script does a best-effort scrape and prints what it finds;
it does NOT overwrite the curated data/degrees.json automatically. Review the
output, then merge real values in.

Usage:
    python scripts/scrape_degrees.py
"""
import json
import re
import sys

import httpx

SOURCES = [
    "https://www.getmyuni.com/college/marwadi-university-rajkot-courses-fees",
    "https://www.careers360.com/university/marwadi-university-rajkot/courses",
    "https://collegedunia.com/university/28764-marwadi-university-mu-rajkot/admission",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# Programs we want to keep (id -> display name). Edit to taste.
WANTED = {
    "btech-cse": "B.Tech Computer Engineering",
    "btech-aiml": "B.Tech Artificial Intelligence",
    "btech-mech": "B.Tech Mechanical Engineering",
    "bpharm": "Bachelor of Pharmacy",
    "bca": "Bachelor of Computer Applications",
    "bba": "Bachelor of Business Administration",
    "bsc-it": "B.Sc Information Technology",
    "mba": "Master of Business Administration",
    "mca": "Master of Computer Applications",
    "mtech-cse-cybersec": "M.Tech Cyber Security",
}


def fetch(url: str) -> str:
    try:
        r = httpx.get(url, headers=HEADERS, timeout=20.0, follow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception as e:  # noqa: BLE001
        print(f"  ! failed {url}: {e}", file=sys.stderr)
        return ""


def find_fees(text: str) -> list[str]:
    """Pull rupee-amount snippets for manual review."""
    text = re.sub(r"<[^>]+>", " ", text)            # strip tags
    text = re.sub(r"\s+", " ", text)
    hits = re.findall(r"(?:Rs\.?|INR|₹)\s?[\d,]+(?:\.\d+)?\s?(?:Lakhs?|L|/-)?", text)
    # de-dup preserving order
    seen, out = set(), []
    for h in hits:
        h = h.strip()
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out[:40]


def main() -> None:
    print("Scraping Marwadi University sources (best-effort)...\n")
    for url in SOURCES:
        print(f"== {url}")
        html = fetch(url)
        if not html:
            continue
        fees = find_fees(html)
        print(f"  fee-like snippets found: {len(fees)}")
        for f in fees[:20]:
            print(f"    • {f}")
        print()

    print("-" * 60)
    print("Curated dataset already lives at data/degrees.json with these 10 ids:")
    for k, v in WANTED.items():
        print(f"  - {k}: {v}")
    print("\nReview the scraped snippets above and update data/degrees.json as needed.")
    print("Then run scripts/translate_degrees.py to refresh the Gujarati (*_gu) fields.")


if __name__ == "__main__":
    main()
