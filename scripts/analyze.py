#!/usr/bin/env python3
"""Build the reproducible research artifact from locally downloaded sources."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backend.science import build_cell_months, eligible_hotspots, fit_extremes, fit_harmonization


def clean_perimeters(records: list[dict]) -> tuple[list[dict], dict]:
    """Remove invalid area/year records and repeated stable identifiers."""
    seen, clean = set(), []
    rejected = {"outside_period": 0, "invalid_area": 0, "duplicate_id": 0}
    for record in records:
        try:
            year = int(record.get("year", 0))
            area = float(record.get("area_ha", 0))
        except (TypeError, ValueError):
            rejected["invalid_area"] += 1
            continue
        if not 2001 <= year <= 2025:
            rejected["outside_period"] += 1
            continue
        if not (0 < area < float("inf")):
            rejected["invalid_area"] += 1
            continue
        identifier = str(record.get("id") or "").strip()
        if identifier and identifier in seen:
            rejected["duplicate_id"] += 1
            continue
        if identifier:
            seen.add(identifier)
        clean.append(record)
    return clean, rejected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", type=int, default=199)
    parser.add_argument("--grid", type=float, default=0.5)
    parser.add_argument("--extremes-only", action="store_true")
    args = parser.parse_args()
    processed = ROOT / "data" / "processed"
    destination = processed / "analysis.json"
    output = json.loads(destination.read_text()) if args.extremes_only and destination.exists() else {}
    if not args.extremes_only:
        hotspots = pd.read_csv(processed / "hotspots.csv", dtype={"acq_time": str, "confidence": str})
        print(f"Analyzing {len(hotspots):,} real archived hotspot detections", flush=True)
        hotspots, output["hotspot_eligibility"] = eligible_hotspots(hotspots)
        print(f"Quality/source rule retains {len(hotspots):,} detections", flush=True)
        boundary_path = processed / "california.geojson"
        boundary = json.loads(boundary_path.read_text()) if boundary_path.exists() else None
        cells = build_cell_months(hotspots, args.grid, boundary=boundary)
        coverage_path = processed / "coverage.json"
        coverage = json.loads(coverage_path.read_text()) if coverage_path.exists() else None
        harmonization, estimator = fit_harmonization(cells, args.grid, coverage=coverage)
        output["harmonization"] = harmonization
        models = ROOT / "models"
        models.mkdir(exist_ok=True)
        with (models / "harmonization.pkl").open("wb") as handle:
            pickle.dump(estimator, handle)
        with (models / "boosted_candidate.pkl").open("wb") as handle:
            pickle.dump(estimator["ml_candidate"], handle)
        print("Harmonization finished; selected:", harmonization["evaluation"]["selected_method"], flush=True)
    raw = json.loads((processed / "perimeters.json").read_text())
    records = raw.get("features", raw.get("records", [])) if isinstance(raw, dict) else raw
    cleaned, rejected = clean_perimeters(records)
    print(f"Fitting tail of {len(cleaned):,} perimeter areas; bootstrap={args.bootstrap}", flush=True)
    output["extremes"] = fit_extremes([r["area_ha"] for r in cleaned], args.bootstrap)
    output["extremes"]["cleaning"] = rejected
    normalize_id = lambda value: str(value or "").strip().strip("{}").lower()
    complex_parent_ids = {normalize_id(r.get("complex_id")) for r in cleaned if r.get("complex_id")}
    def complex_involved(record):
        return bool(record.get("complex_id") or record.get("complex_name") or
                    "COMPLEX" in str(record.get("name", "")).upper() or
                    (normalize_id(record.get("irwin_id")) in complex_parent_ids))
    standalone = [r for r in cleaned if not complex_involved(r)]
    print(f"Complex sensitivity excludes {len(cleaned) - len(standalone):,} linked or named records", flush=True)
    sensitivity = fit_extremes([r["area_ha"] for r in standalone], args.bootstrap)
    sensitivity["definition"] = "Exclude records with complex_id or complex_name, names containing COMPLEX, or IRWIN IDs referenced as complex parents. No automatic collapse by shared IRWIN ID."
    sensitivity["excluded_records"] = len(cleaned) - len(standalone)
    sensitivity["limitation"] = "A metadata-based sensitivity subset, not a complete event genealogy or guarantee of independence."
    output["extremes"]["complex_sensitivity"] = sensitivity
    output["extremes"]["limitations"].append("Main sample consists of reported perimeter records. Complex parents and children can coexist; see the metadata-based complex sensitivity subset.")
    output.update({
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": {"start": "2001-01-01", "end": "2025-12-31"},
        "study_area": "California, USA",
    })
    provenance = ROOT / "data" / "provenance.json"
    if provenance.exists():
        output["provenance"] = json.loads(provenance.read_text())
    output["input_sha256"] = {}
    for filename in ("hotspots.csv", "perimeters.json", "california.geojson", "coverage.json"):
        path = processed / filename
        if path.exists():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
            output["input_sha256"][filename] = digest.hexdigest()
    destination.write_text(json.dumps(output, separators=(",", ":"), allow_nan=False))
    print(f"Saved {destination.relative_to(ROOT)} ({destination.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
