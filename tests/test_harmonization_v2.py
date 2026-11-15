"""Research regressions: target leakage, count support, and geographic transfer."""
import numpy as np
import pandas as pd
import pytest

from backend.harmonization_v2 import CountGAM, SeasonalRatio, metrics
from scripts.train_harmonization_v2 import diagnostics, subset


def sample():
    rng = np.random.default_rng(17)
    n = 720
    count = rng.poisson(4, n).astype(float)
    count[:120] = 0
    month = np.arange(n) % 12 + 1
    frame = pd.DataFrame({"year": 2013 + np.arange(n) // 120, "month": month,
        "date": [f"{2013+i//120}-{m:02d}-01" for i, m in enumerate(month)],
        "state": np.where((np.arange(n)//12) % 2, "CA", "OR"), "ecoregion": np.where(np.arange(n) % 3, "forest", "desert"),
        "modis_count": count, "frp_sum": count * 12, "frp_mean": np.where(count, 12, 0),
        "frp_max": np.where(count, 16, 0), "frp_std": np.where(count, 2, 0), "terra_count": count*.5,
        "day_fraction": np.where(count, .6, 0), "scan_mean": np.where(count, 1, 0), "track_mean": np.where(count, 1, 0),
        "footprint_mean": np.where(count, 1, 0), "hour_sin": np.zeros(n), "hour_cos": np.zeros(n),
        "detection_days": np.minimum(count, 5), "detection_acquisitions": count,
        "latitude": np.full(n, 40), "longitude": np.full(n, -120), "pair_complete": True})
    frame["viirs_count"] = rng.poisson(count*3+.8)
    return frame


@pytest.mark.parametrize("alpha", [0., 1.])
def test_gam_fits_counts_without_target_leakage_and_handles_unseen_regions(alpha):
    frame = sample()
    model = CountGAM(alpha=alpha).fit(frame)
    prediction = model.predict(frame)
    assert model.optimization["success"]
    assert np.isfinite(prediction).all() and (prediction > 0).all()
    # VIIRS and calendar year are evaluation-only, never inference features.
    changed = frame.assign(viirs_count=1e12, year=1900)
    np.testing.assert_allclose(model.predict(changed), prediction)
    # The additive term can predict VIIRS reports where MODIS had zero reports.
    assert prediction[frame.modis_count.eq(0)].mean() > .1
    novel = frame.iloc[:5].assign(state="UNKNOWN", ecoregion="UNSEEN")
    assert np.isfinite(model.predict(novel)).all()
    # Fitted conditional means improve aggregate Poisson deviance over a
    # constant count prediction on this deliberately simple identifiable signal.
    y = frame.viirs_count.to_numpy()
    dev = lambda p: np.mean(p - y*np.log(p))
    assert dev(prediction) < dev(np.full(len(y), y.mean()))


def test_state_calibration_separates_states_and_falls_back_for_unseen_states():
    frame = sample()
    frame.loc[frame.state.eq("OR"), "viirs_count"] *= 5
    model = SeasonalRatio(by_state=True).fit(frame)
    ca = frame[frame.state.eq("CA") & frame.modis_count.gt(0)]
    assert model.predict(ca).sum() < model.predict(ca.assign(state="OR")).sum()
    assert np.isfinite(model.predict(ca.assign(state="NEW"))).all()


def test_missing_targets_and_outages_never_enter_fitting_split():
    frame = sample()
    frame.loc[:4, "pair_complete"] = False
    frame.loc[5:9, "viirs_count"] = np.nan
    selected = subset(frame, [2013, 2014])
    assert set(range(10)).isdisjoint(selected.index)
    assert selected.year.between(2013, 2014).all()
    assert selected.viirs_count.notna().all()


def test_northern_audit_serializes_empty_southern_region_as_unavailable():
    frame = sample()
    result = diagnostics(frame, frame.viirs_count.to_numpy())
    assert result["regions"]["south"] is None
    assert result["monthly_mae"] == 0
    assert result["cell_month_mae"] == 0
    # Statewide score is computed after aggregation, rather than averaging
    # relative errors of many zero-activity cells.
    result = metrics(frame, frame.viirs_count.to_numpy()+1)
    assert result["monthly_mae"] > result["cell_month_mae"]
