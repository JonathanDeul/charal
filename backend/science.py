"""Reproducible research computations for Charal.

Counts are reported detections, not individual fires. Model outputs are estimates
on the Suomi-NPP VIIRS reporting scale; they are not recovered observations.
"""
from __future__ import annotations

import math
from typing import Any, TYPE_CHECKING

import numpy as np
from scipy import optimize, special, stats

if TYPE_CHECKING:
    import pandas as pd
    from sklearn.ensemble import HistGradientBoostingRegressor

ACRE_TO_HA = 0.40468564224
MIN_AREA_HA = 300 * ACRE_TO_HA
FEATURES = [
    "modis_count", "log_modis_count", "log_frp_sum", "frp_mean",
    "day_fraction", "latitude", "longitude", "month_sin", "month_cos",
]


def eligible_hotspots(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One shared quality/thermal-source rule for research and runtime data."""
    import pandas as pd

    required = {"sensor", "confidence", "type"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Quality filtering requires columns {sorted(required)}")
    sensor = frame.sensor.astype(str).str.upper()
    vegetation = pd.to_numeric(frame["type"], errors="coerce").eq(0)
    confidence = frame.confidence.astype(str).str.strip().str.lower()
    accepted = (sensor.eq("MODIS") & pd.to_numeric(confidence, errors="coerce").ge(30)) | (
        sensor.eq("VIIRS") & confidence.isin(["n", "h", "nominal", "high"]))
    keep = vegetation & accepted
    audit = {
        "rule": "type == 0; MODIS numeric confidence >= 30; VIIRS confidence n/h (nominal/high).",
        "raw_records": int(len(frame)), "retained_records": int(keep.sum()),
        "excluded_records": int((~keep).sum()),
        "excluded_nonvegetation_or_untyped": int((~vegetation).sum()),
        "excluded_low_or_unknown_confidence_after_type_filter": int((vegetation & ~accepted).sum()),
        "by_sensor": {
            key: {"raw": int(sensor.eq(key).sum()), "retained": int((keep & sensor.eq(key)).sum())}
            for key in ["MODIS", "VIIRS"]
        },
        "note": "Presumed vegetation fires include agricultural burning. Sensor confidence classes are quality filters, not comparable calibrated probabilities. Archived processing-version changes remain.",
    }
    return frame.loc[keep].copy(), audit


def _finite(values: Any) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    return values[np.isfinite(values) & (values > 0)]


def _pareto_fit(values: np.ndarray, xmin: float) -> tuple[float, float, int]:
    tail = np.sort(values[values >= xmin])
    denominator = np.log(tail / xmin).sum()
    if len(tail) < 2 or denominator <= 0:
        return math.nan, math.inf, len(tail)
    alpha = 1.0 + len(tail) / denominator
    cdf = 1.0 - (tail / xmin) ** (1.0 - alpha)
    n = len(tail)
    ks = float(max(np.max(np.arange(1, n + 1) / n - cdf),
                   np.max(cdf - np.arange(n) / n)))
    return float(alpha), ks, n


def _choose_xmin(values: np.ndarray, floor: float, min_tail: int) -> dict:
    eligible = np.sort(values[values >= floor])
    if len(eligible) < min_tail or len(np.unique(eligible)) < 2:
        return {"xmin": floor, "alpha": None, "ks": None,
                "tail_n": int(len(eligible))}
    # A deterministic grid of observed thresholds bounds the bootstrap cost.
    last_index = max(0, len(eligible) - min_tail)
    positions = np.unique(np.linspace(0, last_index, min(80, last_index + 1)).astype(int))
    candidates = np.unique(np.r_[floor, eligible[positions]])
    fits = []
    for xmin in candidates:
        alpha, ks, n = _pareto_fit(eligible, float(xmin))
        if n >= min_tail and np.isfinite(alpha):
            fits.append({"xmin": float(xmin), "alpha": alpha,
                         "ks": ks, "tail_n": int(n)})
    if not fits:
        return {"xmin": floor, "alpha": None, "ks": None,
                "tail_n": int(len(eligible))}
    return min(fits, key=lambda f: (f["ks"], f["xmin"]))


def _conditional_lognormal(tail: np.ndarray, xmin: float) -> tuple[float, float, np.ndarray]:
    logs = np.log(tail)
    logmin = np.log(xmin)

    def objective(parameters):
        mu, log_sigma = parameters
        sigma = np.exp(log_sigma)
        log_survival = special.log_ndtr((mu - logmin) / sigma)
        logpdf = stats.norm.logpdf(logs, mu, sigma) - logs - log_survival
        return -float(logpdf.sum())

    fit = optimize.minimize(
        objective, [float(logs.mean()), float(np.log(max(logs.std(), 0.2)))],
        method="L-BFGS-B", bounds=[(logmin - 30, logmin + 30), (-4, 4)],
    )
    mu, log_sigma = fit.x
    sigma = float(np.exp(log_sigma))
    logpdf = stats.norm.logpdf(logs, mu, sigma) - logs - special.log_ndtr((mu - logmin) / sigma)
    return float(mu), sigma, np.asarray(logpdf)


def _comparison(logp: np.ndarray, logq: np.ndarray, alternative: str) -> dict:
    difference = logp - logq
    ratio = float(difference.sum())
    spread = float(difference.std(ddof=1)) if len(difference) > 1 else 0.0
    z = ratio / (np.sqrt(len(difference)) * spread) if spread > 1e-12 else 0.0
    p = float(2 * stats.norm.sf(abs(z))) if spread > 1e-12 else 1.0
    favored = "inconclusive" if p >= 0.1 else ("power_law" if ratio > 0 else alternative)
    return {"alternative": alternative, "log_likelihood_ratio": ratio,
            "vuong_z": float(z), "p_value": p, "favored": favored,
            "note": "Approximate two-sided normalized likelihood-ratio test on the same fitted tail; parameters estimated from these data."}


def fit_extremes(
    areas: Any, bootstrap_replicates: int = 199, seed: int = 42,
    min_area_ha: float = MIN_AREA_HA, min_tail: int = 50,
) -> dict:
    """Fit a continuous Pareto tail and two conditional alternatives.

    x_min is chosen by KS minimization above the reporting-size floor. A
    semiparametric bootstrap resamples the empirical body and a model tail,
    and re-fits x_min on every sample. Set bootstrap_replicates=0 for an
    explicitly exploratory, unvalidated interactive AOI fit.
    """
    if min_area_ha <= 0 or min_tail < 3 or bootstrap_replicates < 0:
        raise ValueError("Positive area floor, min_tail >= 3 and nonnegative bootstrap count required")
    cleaned = _finite(areas)
    values = np.sort(cleaned[cleaned >= min_area_ha])
    result = {
        "status": "insufficient_data", "n_events": int(len(cleaned)),
        "n_above_floor": int(len(values)), "minimum_area_ha": float(min_area_ha),
        "minimum_tail_n": int(min_tail), "units": "hectares",
        "seed": int(seed), "bootstrap_replicates": int(bootstrap_replicates),
        "xmin": None, "tail_n": 0, "alpha": None, "alpha_ci": None,
        "alpha_empirical_ci": None,
        "ks": None, "p_value": None, "ccdf": [],
        "lognormal_comparison": None, "exponential_comparison": None,
        "limitations": [
            "Documented final wildfire perimeter area, not satellite hotspot count or precise area actually burned.",
            "The 300-acre floor addresses current CAL FIRE vegetation-dependent size cutoffs; it cannot establish historical completeness.",
            "Missing perimeters, duplicate events, reporting changes, suppression, and regional mixtures can affect the distribution.",
            "A non-small bootstrap p-value is compatibility with a fitted tail, not proof of a power law or self-organized criticality.",
        ],
    }
    fit = _choose_xmin(values, min_area_ha, min_tail)
    result.update(fit)
    if fit["alpha"] is None:
        result["reason"] = "Too few distinct event areas for a stable tail fit."
        return result
    xmin, alpha = fit["xmin"], fit["alpha"]
    tail = np.sort(values[values >= xmin])
    mu, sigma, log_lognormal = _conditional_lognormal(tail, xmin)
    rate = 1.0 / max(float((tail - xmin).mean()), 1e-12)
    log_exponential = np.log(rate) - rate * (tail - xmin)
    log_power = np.log(alpha - 1) - np.log(xmin) - alpha * np.log(tail / xmin)
    result.update({
        "status": "fitted", "lognormal_parameters": {"mu": mu, "sigma": sigma},
        "exponential_rate": rate,
        "lognormal_comparison": _comparison(log_power, log_lognormal, "lognormal"),
        "exponential_comparison": _comparison(log_power, log_exponential, "exponential"),
    })
    curve_x = np.unique(np.r_[np.geomspace(xmin, max(float(tail.max()), xmin * 1.01), 100), tail[-1]])
    lognorm_logsf_min = special.log_ndtr((mu - np.log(xmin)) / sigma)
    result["ccdf"] = [{
        "area_ha": float(x),
        "empirical": float(np.sum(tail >= x) / len(tail)),
        "power_law": float((x / xmin) ** (1 - alpha)),
        "lognormal": float(np.exp(special.log_ndtr((mu - np.log(x)) / sigma) - lognorm_logsf_min)),
        "exponential": float(np.exp(-rate * (x - xmin))),
    } for x in curve_x]
    if bootstrap_replicates:
        rng = np.random.default_rng(seed)
        body = values[values < xmin]
        tail_fraction = len(tail) / len(values)
        ks_values, alphas, thresholds = [], [], []
        for _ in range(bootstrap_replicates):
            n_tail = int(rng.binomial(len(values), tail_fraction))
            n_body = len(values) - n_tail
            sampled_tail = xmin * (1 + rng.pareto(alpha - 1, n_tail))
            sampled_body = rng.choice(body, n_body, replace=True) if len(body) else np.empty(0)
            sample = np.r_[sampled_body, sampled_tail]
            simulated = _choose_xmin(sample, min_area_ha, min_tail)
            if simulated["alpha"] is not None:
                ks_values.append(simulated["ks"])
                alphas.append(simulated["alpha"])
                thresholds.append(simulated["xmin"])
        if ks_values:
            result["p_value"] = float((1 + np.sum(np.asarray(ks_values) >= fit["ks"])) / (len(ks_values) + 1))
            result["alpha_ci"] = [float(x) for x in np.quantile(alphas, [0.025, 0.975])]
            result["xmin_bootstrap_interval"] = [float(x) for x in np.quantile(thresholds, [0.025, 0.975])]
            result["bootstrap_successes"] = len(ks_values)
            result["p_monte_carlo_se"] = float(np.sqrt(result["p_value"] * (1 - result["p_value"]) / (len(ks_values) + 1)))
        empirical_alphas = []
        for _ in range(bootstrap_replicates):
            empirical_sample = rng.choice(values, len(values), replace=True)
            empirical_fit = _choose_xmin(empirical_sample, min_area_ha, min_tail)
            if empirical_fit["alpha"] is not None:
                empirical_alphas.append(empirical_fit["alpha"])
        if empirical_alphas:
            result["alpha_empirical_ci"] = [float(x) for x in np.quantile(empirical_alphas, [0.025, 0.975])]
        result["interval_note"] = "alpha_ci: fitted-model semiparametric bootstrap spread; alpha_empirical_ci: empirical record-resampling percentile interval with threshold refitting. Neither accounts for dependence between perimeter records or historical reporting bias."
        result["bootstrap_status"] = "completed"
    else:
        result["bootstrap_status"] = "not_run"
        result["limitations"].append("Interactive fit: goodness-of-fit bootstrap and exponent interval were not calculated for this area.")
    return result


def build_cell_months(hotspots: pd.DataFrame, grid_degrees: float = 0.5,
                     boundary: dict | None = None) -> pd.DataFrame:
    """Aggregate onto a fixed bounding grid, with explicit sensor availability.

    Zero means zero *reported* detections in this file, not a cloud-free
    observation of no fire. Input is expected already clipped to California.
    """
    import pandas as pd

    if grid_degrees <= 0:
        raise ValueError("grid_degrees must be positive")
    frame = hotspots.copy()
    frame["date"] = pd.to_datetime(frame["acq_date"], errors="coerce")
    frame = frame[frame["date"].between("2001-01-01", "2025-12-31")].copy()
    frame = frame[frame["latitude"].between(32.0, 42.5) & frame["longitude"].between(-125, -113.5)].copy()
    if frame.empty:
        raise ValueError("No California observations within the supported period")
    frame["year"] = frame["date"].dt.year
    frame["month"] = frame["date"].dt.month
    frame["gy"] = np.floor(frame["latitude"] / grid_degrees).astype(int)
    frame["gx"] = np.floor(frame["longitude"] / grid_degrees).astype(int)
    frame["sensor"] = frame["sensor"].astype(str).str.upper()
    frame["frp"] = pd.to_numeric(frame.get("frp", 0), errors="coerce").fillna(0).clip(lower=0)
    frame["day"] = frame.get("daynight", pd.Series("", index=frame.index)).astype(str).str.upper().eq("D").astype(int)
    # The same predefined grid is used in every year. Do not derive cell support
    # from future detections; that would leak the locations of future fires.
    gx = np.arange(math.floor(-125 / grid_degrees), math.ceil(-113.5 / grid_degrees))
    gy = np.arange(math.floor(32 / grid_degrees), math.ceil(42.5 / grid_degrees))
    index = pd.MultiIndex.from_product([range(2001, 2026), range(1, 13), gy, gx], names=["year", "month", "gy", "gx"])
    result = pd.DataFrame(index=index)
    keys = ["year", "month", "gy", "gx"]
    modis = frame[frame.sensor.eq("MODIS")]
    modis_summary = modis.groupby(keys).agg(modis_count=("sensor", "size"), frp_sum=("frp", "sum"), frp_mean=("frp", "mean"), day_fraction=("day", "mean"))
    result = result.join(modis_summary)
    # A separate VIIRS platform is an independent sampling system. Reference
    # explicitly requires SNPP, rather than summing all VIIRS satellites.
    viirs = frame[frame.sensor.eq("VIIRS")].copy()
    if "satellite" in viirs:
        platform = viirs["satellite"].astype(str).str.upper().str.replace("_", "-", regex=False)
        snpp = platform.str.contains("SNPP|S-NPP|SUOMI|^N$|^NPP$", regex=True)
        if not snpp.any():
            raise ValueError("No identifiable Suomi-NPP observations; do not pool VIIRS satellites")
        viirs = viirs[snpp]
    result = result.join(viirs.groupby(keys).size().rename("viirs_count"))
    result = result.fillna(0).reset_index()
    if boundary is not None:
        from shapely.geometry import shape, box
        from shapely.ops import unary_union

        if boundary.get("type") == "FeatureCollection":
            region = unary_union([shape(feature["geometry"]) for feature in boundary["features"]])
        elif boundary.get("type") == "Feature":
            region = shape(boundary["geometry"])
        else:
            region = shape(boundary)
        allowed = {(int(y), int(x)) for y in gy for x in gx
                   if region.intersects(box(x * grid_degrees, y * grid_degrees,
                                            (x + 1) * grid_degrees, (y + 1) * grid_degrees))}
        included = np.fromiter(((y, x) in allowed for y, x in zip(result.gy, result.gx)),
                               dtype=bool, count=len(result))
        result = result[included].reset_index(drop=True)
    # Reject missing whole sensor-years. Filling a truly absent file with zero
    # would manufacture a sensor transition and corrupt calibration.
    for sensor, start in [("MODIS", 2001), ("VIIRS", 2012)]:
        source_frame = modis if sensor == "MODIS" else viirs
        supplied_years = set(source_frame.year)
        missing = set(range(start, 2026)) - supplied_years
        if missing:
            raise ValueError(f"Missing {sensor} years: {sorted(missing)}; acquire or explicitly narrow the study period")
    result.loc[result.year < 2012, "viirs_count"] = np.nan
    result["latitude"] = (result.gy + 0.5) * grid_degrees
    result["longitude"] = (result.gx + 0.5) * grid_degrees
    result["log_modis_count"] = np.log1p(result.modis_count)
    result["log_frp_sum"] = np.log1p(result.frp_sum)
    result["month_sin"] = np.sin(2 * np.pi * result.month / 12)
    result["month_cos"] = np.cos(2 * np.pi * result.month / 12)
    result["date"] = pd.to_datetime(dict(year=result.year, month=result.month, day=1)).dt.strftime("%Y-%m-%d")
    return result


def split_years(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    return (frame.year.between(2013, 2020), frame.year.between(2021, 2022), frame.year.between(2023, 2025))


def _new_model() -> HistGradientBoostingRegressor:
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(loss="poisson", learning_rate=0.065,
                                        max_iter=180, max_leaf_nodes=15,
                                        min_samples_leaf=35, l2_regularization=2,
                                        early_stopping=False, random_state=42)


def _month_ratios(frame: pd.DataFrame) -> dict:
    totals = frame.groupby("month")[["modis_count", "viirs_count"]].sum()
    global_ratio = float(totals.viirs_count.sum() / max(totals.modis_count.sum(), 1))
    return {int(m): float(row.viirs_count / row.modis_count) if row.modis_count else global_ratio for m, row in totals.iterrows()}


def _ratio_predict(frame: pd.DataFrame, ratios: dict) -> np.ndarray:
    return frame.modis_count.to_numpy() * frame.month.map(ratios).to_numpy()


def _metrics(frame: pd.DataFrame, prediction: np.ndarray) -> dict:
    import pandas as pd
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    actual = frame.viirs_count.to_numpy()
    aggregated = pd.DataFrame({"date": frame.date.to_numpy(), "actual": actual, "predicted": prediction}).groupby("date")[["actual", "predicted"]].sum()
    mae = float(mean_absolute_error(aggregated.actual, aggregated.predicted))
    return {
        "monthly_mae": mae,
        "monthly_rmse": float(np.sqrt(mean_squared_error(aggregated.actual, aggregated.predicted))),
        "monthly_wape": float(np.abs(aggregated.actual - aggregated.predicted).sum() / max(aggregated.actual.sum(), 1)),
        "monthly_bias": float((aggregated.predicted - aggregated.actual).mean()),
        "cell_month_mae": float(mean_absolute_error(actual, prediction)),
        "n_months": int(len(aggregated)), "n_cell_months": int(len(frame)),
    }


def fit_harmonization(cells: pd.DataFrame, grid_degrees: float = 0.5,
                      coverage: dict | None = None) -> tuple[dict, Any]:
    """Compare ML, seasonal-ratio and seasonal-climatology controls.

    Select the production method on 2021–2022 validation error, then disclose
    all untouched 2023–2025 test results. Retain the original training fit so
    validation residual bands correspond to the deployed estimator.
    """
    import pandas as pd

    all_reported_evaluation = None
    coverage_lookup = {}
    if coverage is not None:
        # This independent NASA outage policy is not chosen from model errors.
        # Retain original all-report metrics for transparent comparison.
        all_reported_result, _ = fit_harmonization(cells, grid_degrees, coverage=None)
        all_reported_evaluation = all_reported_result["evaluation"]
        del all_reported_result
        coverage_lookup = {row["date"][:7]: row for row in coverage["monthly"]}
        study_dates = set(cells.date.str[:7])
        if study_dates - set(coverage_lookup):
            raise ValueError("Coverage metadata must explicitly cover every study month")
    def missing_count(date, sensor):
        row = coverage_lookup.get(str(date)[:7], {})
        return int(row.get(f"{sensor}_missing_day_count", len(row.get(f"{sensor}_missing_days", []))))
    modis_missing = cells.date.map(lambda date: missing_count(date, "modis")).to_numpy()
    viirs_missing = cells.date.map(lambda date: missing_count(date, "viirs")).to_numpy()
    pair_complete = (modis_missing == 0) & (viirs_missing == 0)
    train_mask, valid_mask, test_mask = split_years(cells)
    train_mask &= pair_complete
    valid_mask &= pair_complete
    test_mask &= pair_complete
    train, valid, test = cells[train_mask], cells[valid_mask], cells[test_mask]
    model = _new_model().fit(train[FEATURES], train.viirs_count)
    ratios = _month_ratios(train)
    valid_ml = np.maximum(model.predict(valid[FEATURES]), 0)
    valid_ratio = _ratio_predict(valid, ratios)
    valid_metrics = {"ml": _metrics(valid, valid_ml), "baseline": _metrics(valid, valid_ratio)}
    selected = "ml" if valid_metrics["ml"]["monthly_mae"] < valid_metrics["baseline"]["monthly_mae"] else "baseline"
    test_ml = np.maximum(model.predict(test[FEATURES]), 0)
    test_ratio = _ratio_predict(test, ratios)
    climatology = train.groupby(["gy", "gx", "month"]).viirs_count.mean()
    test_climatology = test.set_index(["gy", "gx", "month"]).index.map(climatology).to_numpy(dtype=float)
    test_climatology = np.nan_to_num(test_climatology)
    metrics = {"ml": _metrics(test, test_ml), "baseline": _metrics(test, test_ratio), "seasonal": _metrics(test, test_climatology)}
    # A geographically held-out northern block, in addition to future years.
    south_train = train[train.latitude < 39.5]
    north_test = test[test.latitude >= 39.5]
    spatial_model = _new_model().fit(south_train[FEATURES], south_train.viirs_count)
    spatial_metrics = {
        "definition": "Train 2013–2020 south of 39.5°N; test 2023–2025 at or north of 39.5°N.",
        "ml": _metrics(north_test, np.maximum(spatial_model.predict(north_test[FEATURES]), 0)),
        "baseline": _metrics(north_test, _ratio_predict(north_test, _month_ratios(south_train))),
    }
    validation_prediction = valid_ml if selected == "ml" else valid_ratio
    normalized_error = np.abs(valid.viirs_count.to_numpy() - validation_prediction) / np.sqrt(validation_prediction + 1)
    cell_q = float(np.quantile(normalized_error, 0.8))
    validation_month = pd.DataFrame({"date": valid.date.to_numpy(), "actual": valid.viirs_count.to_numpy(), "prediction": validation_prediction}).groupby("date").sum()
    monthly_q = float(np.quantile(np.abs(validation_month.actual - validation_month.prediction), 0.8))
    selected_test_prediction = test_ml if selected == "ml" else test_ratio
    test_monthly = pd.DataFrame({"date": test.date.to_numpy(), "actual": test.viirs_count.to_numpy(), "prediction": selected_test_prediction}).groupby("date").sum()
    test_band_coverage = float(np.mean(np.abs(test_monthly.actual - test_monthly.prediction) <= monthly_q))
    # Retain the training estimator; validation remains independent for its
    # residual bands. Test years remain absent from all fitting and selection.
    final_model = model if selected == "ml" else None
    final_ratios = ratios
    model_prediction = np.maximum(final_model.predict(cells[FEATURES]), 0) if final_model is not None else _ratio_predict(cells, final_ratios)
    output = cells[["date", "year", "month", "latitude", "longitude", "modis_count", "viirs_count"]].copy()
    output["modeled_count"] = model_prediction
    reference_available = (output.year > 2012) | ((output.year == 2012) & (output.month >= 2))
    output["harmonized_count"] = np.where(reference_available, output.viirs_count, model_prediction)
    output["source"] = np.where(reference_available, "observed_viirs", "modeled_modis")
    width = cell_q * np.sqrt(model_prediction + 1)
    output["lower"] = np.where(reference_available, np.nan, np.maximum(model_prediction - width, 0))
    output["upper"] = np.where(reference_available, np.nan, model_prediction + width)
    output["modis_missing_day_count"] = modis_missing
    output["viirs_missing_day_count"] = viirs_missing
    output["reference_complete"] = reference_available & (viirs_missing == 0)
    output["modis_complete"] = modis_missing == 0
    reference_gap = reference_available & (viirs_missing > 0)
    historic_modis_gap = ~reference_available & (modis_missing > 0)
    output.loc[reference_gap, "source"] = "incomplete_reference"
    output.loc[historic_modis_gap, "source"] = "incomplete_modis"
    output["known_gap"] = reference_gap | historic_modis_gap
    output.loc[output.known_gap, ["harmonized_count", "lower", "upper"]] = np.nan
    # Omit fixed empty cells in JSON without changing the training grid.
    supported = cells.groupby(["gy", "gx"])[["modis_count", "viirs_count"]].sum().sum(axis=1)
    active = set(supported[supported > 0].index)
    active_mask = np.fromiter(((gy, gx) in active for gy, gx in zip(cells.gy, cells.gx)), dtype=bool, count=len(cells))
    # Include nonzero model output even where no detections ever occurred;
    # dropping it would change the regional modeled totals in the UI.
    publish_mask = active_mask | (model_prediction > 1e-8)
    monthly = output.groupby(["date", "year", "month"], as_index=False).agg(
        modis_count=("modis_count", "sum"),
        viirs_count=("viirs_count", lambda s: s.sum(min_count=1)),
        harmonized_count=("harmonized_count", lambda s: s.sum(min_count=1)), modeled_count=("modeled_count", "sum"), source=("source", "first"),
        modis_missing_day_count=("modis_missing_day_count", "first"), viirs_missing_day_count=("viirs_missing_day_count", "first"),
        reference_complete=("reference_complete", "first"), modis_complete=("modis_complete", "first"), known_gap=("known_gap", "first"))
    monthly["lower"] = np.where(monthly.source.eq("modeled_modis"), np.maximum(monthly.modeled_count - monthly_q, 0), np.nan)
    monthly["upper"] = np.where(monthly.source.eq("modeled_modis"), monthly.modeled_count + monthly_q, np.nan)
    # Keep January 2012's partial raw reference but mark it explicitly.
    monthly["partial_reference"] = (monthly.year == 2012) & (monthly.month == 1)
    monthly["modis_missing_days"] = monthly.date.map(lambda date: coverage_lookup.get(date[:7], {}).get("modis_missing_days", []))
    monthly["viirs_missing_days"] = monthly.date.map(lambda date: coverage_lookup.get(date[:7], {}).get("viirs_missing_days", []))
    monthly["viirs_preoperational_days"] = monthly.date.map(lambda date: coverage_lookup.get(date[:7], {}).get("viirs_preoperational_days", []))
    comparison = pd.DataFrame({"date": test.date.to_numpy(), "actual": test.viirs_count.to_numpy(), "ml": test_ml, "baseline": test_ratio, "seasonal": test_climatology}).groupby("date", as_index=False).sum()
    result = {
        "reference": "Suomi-NPP VIIRS 375 m reported hotspot detections",
        "grid_degrees": float(grid_degrees),
        "units": "reference-equivalent detections per cell-month",
        "monthly": _records(monthly), "cell_monthly": _records(output[publish_mask]),
        "evaluation": {
            "train_years": list(range(2013, 2021)), "validation_years": [2021, 2022],
            "test_years": [2023, 2024, 2025], "metrics": metrics,
            "validation_metrics": valid_metrics, "selected_method": selected,
            "selection_rule": "Lower statewide monthly MAE on validation years only.",
            "spatial_check": spatial_metrics, "monthly_test": _records(comparison),
            "final_training_years": list(range(2013, 2021)),
            "coverage_policy": "Exclude a paired cell-month from model fitting, validation and test if NASA lists any missing MODIS or Suomi-NPP day in that month. No error-based exclusion; no listed gap does not imply cloud-free exposure.",
            "excluded_months": sorted({date[:7] for date, complete in zip(cells.date, pair_complete) if not complete and int(date[:4]) >= 2013}),
            "eligible_months": {"training": sorted(set(train.date.str[:7])), "validation": sorted(set(valid.date.str[:7])), "test": sorted(set(test.date.str[:7]))},
            "baseline": "Month-specific VIIRS/MODIS count ratios estimated only from training years.",
            "seasonal": "Cell/month VIIRS mean from training years; no MODIS input.",
        },
        "model": {"type": "HistGradientBoostingRegressor", "loss": "poisson", "features": FEATURES,
                  "random_seed": 42, "parameters": _new_model().get_params()},
        "uncertainty": {"label": "80% validation-residual band", "cell_standardized_abs_error_q80": cell_q,
                        "statewide_month_abs_error_q80": monthly_q,
                        "test_monthly_band_coverage": test_band_coverage,
                        "calibration_months": int(len(validation_month)),
                        "note": "Empirical 2021–2022 residual scale; not a confidence interval or guaranteed coverage. Cell bands must not be summed into a regional interval."},
        "limitations": [
            "The reference is a detection/reporting scale, not true fire count or burned area.",
            "Observed VIIRS replaces the modeled series from February 2012 onward; January 2012 was only partly observed.",
            "Historical MODIS-derived values are model backcasts, not actual VIIRS observations; missing small fires cannot be individually reconstructed.",
            "Zero cell counts mean no reports in the archive. Cloud-free exposure and complete orbit sampling are not available from hotspot CSVs alone.",
            "MODIS and VIIRS have different overpass times, sensitivities and geometry; this empirical calibration cannot remove all observational bias.",
            "Models trained after 2012 assume transferable historical relationships; orbit drift and fire-regime changes can violate that assumption.",
            "0.5-degree cells approximate an AOI by their centers; an arbitrary AOI is not an exact clipped-pixel analysis.",
            "Archived MODIS product-version strings change across the record; calibration does not establish a uniformly reprocessed collection.",
            "Independent NASA global-outage metadata masks known-incomplete reference months; it does not measure clouds, local exposure, all partial-day outages or historical platform sampling differences.",
        ],
    }
    if all_reported_evaluation is not None:
        result["evaluation"]["all_reported_months"] = all_reported_evaluation
        result["coverage"] = {key: value for key, value in coverage.items() if key != "monthly"}
    return result, {"model": final_model, "ml_candidate": model, "ratios": final_ratios,
                    "features": FEATURES, "selected_method": selected}


def _records(frame: pd.DataFrame) -> list[dict]:
    """JSON-safe records, retaining null for unavailable measurements."""
    return frame.astype(object).where(frame.notna(), None).to_dict("records")
