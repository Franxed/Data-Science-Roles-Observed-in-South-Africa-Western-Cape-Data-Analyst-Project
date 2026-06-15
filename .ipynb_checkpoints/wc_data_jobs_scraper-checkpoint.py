"""
Western Cape Data Jobs Scraper  ·  v3
======================================
Scrapes job listings from Indeed (primary) and LinkedIn (secondary).
Glassdoor is intentionally excluded — it returns 403 errors reliably in 2025.

Install:
    pip install python-jobspy pandas

Run:
    python wc_data_jobs_scraper.py

Output:
    wc_data_jobs_YYYYMMDD_HHMM.csv  in the current directory.

Notes:
    • Indeed  → no rate-limiting, most reliable for ZA
    • LinkedIn → rate-limits at ~page 10; scrape fewer roles at a time if blocked
    • If you get 429 errors, wait 10–15 min and reduce RESULTS_PER_ROLE to 20
"""

import csv
import time
import random
import pandas as pd
from datetime import datetime

try:
    from jobspy import scrape_jobs
except ImportError:
    raise SystemExit("jobspy not installed. Run:  pip install python-jobspy")

# ── Configuration  ─────────────────────────────────────────────────────────────

LOCATION = "Cape Town, Western Cape, South Africa"
COUNTRY_CODE = "south africa"  # jobspy country hint for Indeed
DAYS_OLD = 14  # posts within the last N days
RESULTS_PER_ROLE = 40  # per role, per source — keep ≤50 to avoid blocks

# Indeed only is safest; add "linkedin" if you want more volume
# DO NOT add "glassdoor" — it returns 403 in 2025
SOURCES = ["indeed", "linkedin"]

# Roles to search. Grouped so related terms run together, helping dedup.
JOB_ROLES = [
    # Core data roles
    "Data Analyst",
    "Data Scientist",
    "Data Engineer",
    # ML / AI
    "Machine Learning Engineer",
    "AI Engineer",
    # BI / reporting
    "Business Intelligence Analyst",
    "Analytics Engineer",
    # Broader roles that often appear in WC market
    "Business Analyst",
    "Data Architect",
]

# Delay between role requests (seconds). Randomised to avoid pattern detection.
DELAY_MIN = 4
DELAY_MAX = 9


# ── Scraper ────────────────────────────────────────────────────────────────────

def scrape_role(role: str, index: int, total: int) -> pd.DataFrame:
    """Scrape a single role from all configured sources."""
    print(f"\n[{index}/{total}] Scraping: '{role}' ...")

    try:
        df = scrape_jobs(
            site_name=SOURCES,
            search_term=role,
            location=LOCATION,
            results_wanted=RESULTS_PER_ROLE,
            hours_old=DAYS_OLD * 24,
            country_indeed=COUNTRY_CODE,
            # linkedin_fetch_description is OFF — speeds up scraping and reduces
            # the chance of hitting LinkedIn's rate limit (it doubles requests)
            linkedin_fetch_description=False,
            verbose=0,  # set to 1 to see per-source debug output
        )

        if df.empty:
            print(f"  ⚠  No results for '{role}'. Site may have blocked the request.")
            return pd.DataFrame()

        df.insert(0, "search_role", role)
        print(f"  ✓ {len(df)} listings found.")
        return df

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return pd.DataFrame()


def build_dataset(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Combine all role frames, deduplicate, and select analysis-ready columns."""

    combined = pd.concat([f for f in frames if not f.empty], ignore_index=True)

    if combined.empty:
        return combined

    # ── Deduplication ──────────────────────────────────────────────────────────
    # Same posting often surfaces under multiple search terms or sources.
    # Dedup on URL first; fall back to title+company fingerprint.
    before = len(combined)

    if "job_url" in combined.columns:
        combined = combined.drop_duplicates(subset=["job_url"], keep="first")

    # Secondary dedup: identical title + company (catches same job on 2 sources)
    if {"title", "company"}.issubset(combined.columns):
        combined = combined.drop_duplicates(
            subset=["title", "company"], keep="first"
        )

    removed = before - len(combined)
    if removed:
        print(f"\n  Removed {removed} duplicate listing(s).")

    # ── Column selection ───────────────────────────────────────────────────────
    keep = [
        "search_role",
        "site",
        "title",
        "company",
        "location",
        "job_type",
        "is_remote",
        "date_posted",
        "min_amount",  # salary (numeric, ready for analysis)
        "max_amount",
        "currency",
        "interval",  # yearly / monthly / hourly
        "description",  # full text — useful for NLP / keyword analysis
        "job_url",
    ]
    available = [c for c in keep if c in combined.columns]
    combined = combined[available].copy()

    # ── Cleaning ───────────────────────────────────────────────────────────────
    for col in ["title", "company", "location"]:
        if col in combined.columns:
            combined[col] = combined[col].astype(str).str.strip()

    # Standardise date column to ISO format strings (avoids Excel timezone issues)
    if "date_posted" in combined.columns:
        combined["date_posted"] = pd.to_datetime(
            combined["date_posted"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")

    combined["scraped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return combined.reset_index(drop=True)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    total = len(JOB_ROLES)

    print("=" * 62)
    print("  Western Cape Data Jobs Scraper  ·  v3")
    print(f"  Roles    : {total}")
    print(f"  Sources  : {', '.join(SOURCES)}")
    print(f"  Location : {LOCATION}")
    print(f"  Days old : ≤ {DAYS_OLD}")
    print(f"  Max/role : {RESULTS_PER_ROLE} per source")
    print("=" * 62)

    all_frames = []

    for i, role in enumerate(JOB_ROLES, start=1):
        frame = scrape_role(role, i, total)
        all_frames.append(frame)

        # Polite delay between requests — skip after the last role
        if i < total:
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            print(f"  ↳ Waiting {delay:.1f}s before next request...")
            time.sleep(delay)

    # ── Combine & save ─────────────────────────────────────────────────────────
    print("\n  Processing results...")
    combined = build_dataset(all_frames)

    if combined.empty:
        print("\n⚠  No jobs collected.")
        print("   Try: increasing DAYS_OLD, reducing RESULTS_PER_ROLE, or waiting")
        print("   15 minutes if you were rate-limited.")
        return

    filename = f"wc_data_jobs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    # QUOTE_NONNUMERIC ensures description text with commas is safely escaped
    combined.to_csv(
        filename,
        index=False,
        encoding="utf-8-sig",  # opens cleanly in Excel
        quoting=csv.QUOTE_NONNUMERIC,
    )

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 62)
    print(f"  ✓ Total unique listings : {len(combined)}")
    print(f"  ✓ Saved to              : {filename}")
    print("=" * 62)

    if "site" in combined.columns:
        print("\n  By source:")
        print(combined["site"].value_counts().to_string())

    if "search_role" in combined.columns:
        print("\n  By search role:")
        print(combined["search_role"].value_counts().to_string())

    if "is_remote" in combined.columns:
        remote_count = combined["is_remote"].sum()
        print(f"\n  Remote-friendly : {int(remote_count)} listings")

    if "min_amount" in combined.columns:
        salary_rows = combined["min_amount"].dropna()
        if not salary_rows.empty:
            print(f"\n  Salary data available for {len(salary_rows)} listings")
            print(f"    Min floor : R{salary_rows.min():,.0f}")
            print(f"    Max floor : R{salary_rows.max():,.0f}")


if __name__ == "__main__":
    main()