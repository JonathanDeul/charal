"""Statistical invariants and leakage boundaries, using deterministic fixtures."""
import json
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from backend.science import (
    ACRE_TO_HA, MIN_AREA_HA, _month_ratios, build_cell_months,
    eligible_hotspots, fit_extremes, fit_harmonization, split_years,
)


def observations():
    rows = []
    for year in range(2001, 2026):
        rows.append(dict(latitude=38.1, longitude=-121.2, acq_date=f"{year}-08-12",
                         sensor="MODIS", satellite="Terra", frp=3, daynight="D"))
        if year >= 2012:
            rows.append(dict(latitude=38.1, longitude=-121.2, acq_date=f"{year}-08-12",
                             sensor="VIIRS", satellite="SNPP", frp=1, daynight="N"))
    return pd.DataFrame(rows)


def test_reporting_floor_units():
    assert ACRE_TO_HA == pytest.approx(0.40468564224)
    assert MIN_AREA_HA == pytest.approx(121.405692672)


def test_quality_filter_is_sensor_specific_and_excludes_static_sources():
    frame = pd.DataFrame([
        {"sensor": "MODIS", "confidence": "30", "type": 0},
        {"sensor": "MODIS", "confidence": "29", "type": 0},
        {"sensor": "MODIS", "confidence": "100", "type": 2},
        {"sensor": "VIIRS", "confidence": "N", "type": 0},
        {"sensor": "VIIRS", "confidence": "h", "type": 0},
        {"sensor": "VIIRS", "confidence": "l", "type": 0},
        {"sensor": "VIIRS", "confidence": "h", "type": 1},
    ])
    filtered, audit = eligible_hotspots(frame)
    assert filtered.index.tolist() == [0, 3, 4]
    assert audit["raw_records"] == 7
    assert audit["retained_records"] == 3
    assert audit["excluded_nonvegetation_or_untyped"] == 2


def test_pareto_parameter_recovery_and_scale_invariance():
    rng = np.random.default_rng(17)
    areas = MIN_AREA_HA * (1 + rng.pareto(1.3, 6000))
    result = fit_extremes(areas, bootstrap_replicates=0)
    scaled = fit_extremes(areas * 1000, bootstrap_replicates=0, min_area_ha=MIN_AREA_HA * 1000)
    assert result["alpha"] == pytest.approx(2.3, abs=0.12)
    assert result["alpha"] == pytest.approx(scaled["alpha"], abs=1e-10)
    assert result["xmin"] * 1000 == pytest.approx(scaled["xmin"])
    assert result["bootstrap_status"] == "not_run"
    assert result["p_value"] is None
    assert result["alpha_ci"] is None


def test_bootstrap_curve_and_json_are_valid():
    rng = np.random.default_rng(24)
    areas = MIN_AREA_HA * (1 + rng.pareto(1.5, 500))
    result = fit_extremes(areas, bootstrap_replicates=19)
    assert 0 < result["p_value"] <= 1
    assert result["alpha_ci"][0] < result["alpha_ci"][1]
    assert result["alpha_empirical_ci"][0] < result["alpha_empirical_ci"][1]
    assert result["bootstrap_successes"] == 19
    for field in ["empirical", "power_law", "lognormal", "exponential"]:
        values = np.array([point[field] for point in result["ccdf"]])
        assert np.all((values >= 0) & (values <= 1 + 1e-12))
        assert np.all(np.diff(values) <= 1e-12)
    json.dumps(result, allow_nan=False)


def test_insufficient_or_degenerate_tail_is_not_a_claim():
    for areas in [[], [np.nan, -10, 0, np.inf], [200.0] * 100, np.arange(1, 30)]:
        result = fit_extremes(areas, bootstrap_replicates=0)
        assert result["status"] == "insufficient_data"
        assert result["alpha"] is None
        assert result["p_value"] is None


def test_paper_minimum_tail_count_is_enforced():
    result = fit_extremes(np.linspace(150, 1000, 49), bootstrap_replicates=0)
    assert result["status"] == "insufficient_data"
    assert result["n_above_floor"] == 49


def test_calendar_keeps_pre_viirs_unavailable_and_platforms_separate():
    frame = observations()
    extra = frame[(frame.sensor == "VIIRS") & (frame.acq_date >= "2018-01-01")].copy()
    extra["satellite"] = "NOAA-20"
    # These second-platform observations must never double the reference.
    cells = build_cell_months(pd.concat([frame, extra], ignore_index=True))
    assert cells[cells.year < 2012].viirs_count.isna().all()
    assert cells[cells.year == 2025].viirs_count.sum() == 1
    assert cells[cells.year == 2001].modis_count.sum() == 1
    assert set(cells.year) == set(range(2001, 2026))


def test_missing_sensor_year_cannot_be_silently_zero_filled():
    frame = observations()
    frame = frame[~((frame.sensor == "MODIS") & frame.acq_date.str.startswith("2007"))]
    with pytest.raises(ValueError, match="Missing MODIS years"):
        build_cell_months(frame)


def test_boundary_mask_uses_geography_without_losing_border_counts():
    boundary = {"type": "Polygon", "coordinates": [[[-121.3, 38.0], [-121.1, 38.0], [-121.1, 38.2], [-121.3, 38.2], [-121.3, 38.0]]]}
    cells = build_cell_months(observations(), boundary=boundary)
    assert cells.modis_count.sum() == 25
    assert cells.viirs_count.sum() == 14
    # Retain intersecting cells even though their centers are outside polygon.
    assert cells.longitude.nunique() == 1
    assert cells.latitude.nunique() <= 2


def test_year_splits_do_not_leak_and_ratio_uses_only_supplied_training():
    cells = build_cell_months(observations())
    train, validation, test = split_years(cells)
    assert not (train & validation).any()
    assert not (train & test).any()
    assert not (validation & test).any()
    assert cells[train].year.max() < cells[validation].year.min()
    assert cells[validation].year.max() < cells[test].year.min()
    ratios = _month_ratios(cells[train])
    changed = cells.copy()
    changed.loc[validation | test, "viirs_count"] = 1e9
    assert _month_ratios(changed[train]) == ratios


def test_lightweight_api_import_does_not_require_training_libraries():
    result = subprocess.run(
        [sys.executable, "-c", "import sys; import backend.science; assert 'pandas' not in sys.modules; assert 'sklearn' not in sys.modules"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_harmonization_totals_provenance_and_heldout_contract():
    rng = np.random.default_rng(10)
    records = []
    for year in range(2001, 2026):
        for month in range(1, 13):
            for latitude in [38.25, 40.25]:
                count = int(rng.integers(0, 30))
                records.append({
                    "date": f"{year}-{month:02d}-01", "year": year, "month": month,
                    "gy": int(latitude * 2), "gx": -243, "latitude": latitude,
                    "longitude": -121.25, "modis_count": count,
                    "log_modis_count": np.log1p(count), "log_frp_sum": np.log1p(count * 3),
                    "frp_mean": 3, "day_fraction": 0.5,
                    "month_sin": np.sin(2 * np.pi * month / 12),
                    "month_cos": np.cos(2 * np.pi * month / 12),
                    "viirs_count": count * 4 + 2 if year >= 2012 else np.nan,
                })
    coverage = {"monthly": []}
    for year in range(2001, 2026):
        for month in range(1, 13):
            date = f"{year}-{month:02d}"
            coverage["monthly"].append({"date": date,
                "modis_missing_days": ["2010-03-10"] if date == "2010-03" else [],
                "viirs_missing_days": ["2024-07-10", "2024-07-11"] if date == "2024-07" else [],
            })
    result, _ = fit_harmonization(pd.DataFrame(records), coverage=coverage)
    assert result["evaluation"]["test_years"] == [2023, 2024, 2025]
    assert result["evaluation"]["final_training_years"][-1] == 2020
    monthly = {r["date"]: r for r in result["monthly"]}
    assert monthly["2012-01-01"]["source"] == "modeled_modis"
    assert monthly["2012-01-01"]["partial_reference"] is True
    assert monthly["2012-02-01"]["source"] == "observed_viirs"
    assert monthly["2010-03-01"]["viirs_count"] is None
    assert monthly["2010-03-01"]["source"] == "incomplete_modis"
    assert monthly["2010-03-01"]["harmonized_count"] is None
    assert monthly["2024-07-01"]["source"] == "incomplete_reference"
    assert monthly["2024-07-01"]["harmonized_count"] is None
    assert monthly["2024-07-01"]["viirs_count"] > 0
    assert monthly["2024-07-01"]["viirs_missing_day_count"] == 2
    assert monthly["2024-07-01"]["reference_complete"] is False
    assert result["evaluation"]["metrics"]["ml"]["n_months"] == 35
    assert result["evaluation"]["all_reported_months"]["metrics"]["ml"]["n_months"] == 36
    assert monthly["2025-08-01"]["lower"] is None
    cell_totals = {}
    for row in result["cell_monthly"]:
        if row["harmonized_count"] is not None:
            cell_totals[row["date"]] = cell_totals.get(row["date"], 0) + row["harmonized_count"]
    for date, total in cell_totals.items():
        assert total == pytest.approx(monthly[date]["harmonized_count"])
    json.dumps(result, allow_nan=False)
