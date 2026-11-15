#!/usr/bin/env python3
"""Acquire NASA FIRMS' listed missing standard-data dates, without credentials.

These are database-level flags, not an AOI-specific cloud/overpass exposure map.
The HTML page's own documented AJAX endpoint provides all displayed table rows.
Only the first two columns (Standard Data) are parsed; NRT columns are ignored.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import ssl
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
OUTPUT = ROOT / "data/processed/coverage.json"
SOURCE = "https://firms.modaps.eosdis.nasa.gov/api/missing_data/"
DATA_SOURCE = SOURCE + "?action=fetch_data"
SATELLITES = {"Terra (MODIS)": "Terra", "Aqua (MODIS)": "Aqua", "Suomi NPP (VIIRS)": "Suomi NPP"}


class Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.row: list[str] = []
        self.cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td":
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and len(self.row) == 4:
            self.rows.append(self.row)


def fetch(url: str, ajax: bool = False) -> bytes:
    context = ssl.create_default_context(cafile="/etc/ssl/cert.pem" if Path("/etc/ssl/cert.pem").exists() else None)
    headers = {"User-Agent": "California-SpaceApps-research-PoC/1.0"}
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=context, timeout=90) as response:
        return response.read()


def prepare(page: bytes, response: bytes) -> dict:
    payload = json.loads(response)
    if payload.get("success") is not True or not isinstance(payload.get("html"), str):
        raise ValueError("NASA missing-data response was not successful")
    parser = Rows()
    parser.feed(payload["html"])
    if payload.get("rowCount") != len(parser.rows):
        raise ValueError("Parsed row count does not match NASA response")
    flagged = {satellite: set() for satellite in SATELLITES.values()}
    excluded_satellites: dict[str, int] = {}
    for row in parser.rows:
        date_text, label = row[:2]  # STANDARD ONLY; columns 3/4 are NRT.
        date.fromisoformat(date_text)  # Reject malformed/non-date table rows.
        if not "2001-01-01" <= date_text <= "2025-12-31":
            continue
        if label not in SATELLITES:
            excluded_satellites[label] = excluded_satellites.get(label, 0) + 1
            continue
        flagged[SATELLITES[label]].add(date_text)
    monthly = []
    for year in range(2001, 2026):
        for month in range(1, 13):
            key = f"{year}-{month:02d}"
            terra = sorted(d for d in flagged["Terra"] if d.startswith(key))
            aqua = sorted(d for d in flagged["Aqua"] if d.startswith(key))
            viirs = sorted(d for d in flagged["Suomi NPP"] if d.startswith(key))
            modis = sorted(set(terra) | set(aqua))
            startup = [f"2012-01-{day:02d}" for day in range(1, 20)] if key == "2012-01" else []
            status = ("not_yet_available" if key < "2012-01" else "partial_startup" if startup
                      else "known_gap" if viirs else "no_listed_gap")
            monthly.append({"date": key, "modis_missing_days": modis, "viirs_missing_days": viirs,
                            "modis_missing_day_count": len(modis), "viirs_missing_day_count": len(viirs),
                            "modis_platform_days": {"Terra": terra, "Aqua": aqua},
                            "modis_platform_missing_day_count": len(terra) + len(aqua),
                            "modis_both_platform_missing_days": sorted(set(terra) & set(aqua)),
                            "viirs_preoperational_days": startup, "viirs_reference_status": status})
    # Save the fully populated source table, alongside the exact AJAX response.
    rendered, matches = re.subn(r'(<tbody\s+id="table-body"[^>]*>).*?(</tbody>)',
                               lambda m: m.group(1) + payload["html"] + m.group(2),
                               page.decode(), count=1, flags=re.DOTALL)
    if matches != 1:
        raise ValueError("Could not locate the source page table body")
    (RAW / "missing_data.html").write_text(rendered)
    return {
        "source": SOURCE,
        "source_url": SOURCE,
        "table_data_url": DATA_SOURCE,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "period": ["2001-01", "2025-12"],
        "source_columns": "Standard Data: Date Missing and Satellite (Sensor); Near Real Time columns excluded",
        "listed_standard_rows_total": len(parser.rows),
        "selected_satellite_date_count": {sat: len(days) for sat, days in flagged.items()},
        "excluded_standard_rows_in_period_by_satellite": excluded_satellites,
        "flagged_dates_by_satellite": {sat: sorted(days) for sat, days in flagged.items()},
        "raw_page_sha256": hashlib.sha256(page).hexdigest(),
        "raw_response_sha256": hashlib.sha256(response).hexdigest(),
        "viirs_startup_source": "https://firms.modaps.eosdis.nasa.gov/download/",
        "viirs_startup_note": "FIRMS lists Suomi-NPP coverage beginning 20 January 2012. January 1–19 are separately marked preoperational, not attributed to the missing-data table.",
        "supplemental_notices": [{
            "date": "2024-07-24", "satellite": "Suomi NPP", "sensor": "VIIRS",
            "start_utc": "2024-07-24T05:28:00Z", "end_utc": "2024-07-24T18:22:00Z",
            "source": "https://forum.earthdata.nasa.gov/viewtopic.php?p=19854&t=5795",
            "published_date": "2024-07-30",
            "note": "LP DAAC reports a partial-day mission outage and suspended VIIRS processing. This supplementary notice is not a row in the acquired FIRMS Standard Data missing-days table and has not been added to those table-derived day arrays."
        }],
        "monthly": monthly,
        "limitations": [
            "These are all listed historical Standard Data dates for the selected satellites in the table acquired at downloaded_at; the table is not a proof of exhaustive historical outage reporting.",
            "A listed date identifies missing data in the FIRMS database for that satellite/product; it does not establish that every global granule or every California overpass was absent on that date.",
            "A month with no listed dates is not proven complete, cloud-free, or equally observed. Cloud, smoke, view geometry, unlisted/partial outages, and acquisition schedules remain unmeasured by this table.",
            "MODIS missing_days is the union of Terra/Aqua flagged dates. One platform being flagged does not imply both platforms were absent; per-platform arrays and the intersection are supplied separately.",
            "Duplicate rows for a date/platform are collapsed. NOAA-20/NOAA-21 and Near Real Time records are excluded because this snapshot uses standard MODIS and Suomi-NPP data.",
            "Reference availability before Suomi-NPP's start is not represented by zero missing days: viirs_reference_status is not_yet_available before January 2012, and January 2012 has separately documented preoperational days.",
            "Do not convert these day counts into an inverse-coverage scaling factor or corrected hotspot count without a spatial observation model."
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Reparse cached source page and AJAX response")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    shell = RAW / "missing_data_shell.html"
    raw_response = RAW / "missing_data_response.json"
    if args.offline:
        # Initial acquisition may have preserved the untouched shell under the
        # final filename; subsequent runs preserve shell and populated versions.
        page = shell.read_bytes() if shell.exists() else (RAW / "missing_data.html").read_bytes()
        response = raw_response.read_bytes()
    else:
        page = fetch(SOURCE)
        response = fetch(DATA_SOURCE, ajax=True)
    shell.write_bytes(page)
    raw_response.write_bytes(response)
    result = prepare(page, response)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2))
    print("Parsed", result["listed_standard_rows_total"], "source Standard Data rows into", len(result["monthly"]), "months")
    print("Unique historical dates by platform:", result["selected_satellite_date_count"])
    july = next(m for m in result["monthly"] if m["date"] == "2024-07")
    print("Suomi-NPP July 2024 listed dates:", ", ".join(july["viirs_missing_days"]))


if __name__ == "__main__":
    main()
