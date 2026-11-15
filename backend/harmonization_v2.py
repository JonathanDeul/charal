"""Offline, baseline-anchored count calibration. No VIIRS predictor features.

The GAM is a penalized maximum-likelihood model with Gaussian shrinkage on
region effects (MAP partial pooling), not a Bayesian posterior sampler.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize, special
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, SplineTransformer, StandardScaler
from sklearn.ensemble import HistGradientBoostingRegressor

NUMERIC = ["log_modis", "log_frp", "log_frp_mean", "log_frp_max", "log_frp_std",
           "terra_fraction", "day_fraction", "scan_mean", "track_mean", "footprint_mean",
           "hour_sin", "hour_cos", "log_detection_days", "log_detection_acquisitions"]


def predictors(frame):
    x = frame.copy()
    for source, dest in [("modis_count", "log_modis"), ("frp_sum", "log_frp"),
                         ("frp_mean", "log_frp_mean"), ("frp_max", "log_frp_max"),
                         ("frp_std", "log_frp_std"), ("detection_days", "log_detection_days"),
                         ("detection_acquisitions", "log_detection_acquisitions")]:
        x[dest] = np.log1p(x[source].clip(lower=0))
    x["terra_fraction"] = x.terra_count / x.modis_count.clip(lower=1)
    x["month_sin"] = np.sin(x.month * 2 * np.pi / 12)
    x["month_cos"] = np.cos(x.month * 2 * np.pi / 12)
    return x


class SeasonalRatio:
    def __init__(self, by_state=False):
        self.by_state = by_state

    def fit(self, frame):
        totals = frame.groupby("month")[["modis_count", "viirs_count"]].sum()
        self.global_ratio = frame.viirs_count.sum() / max(frame.modis_count.sum(), 1)
        self.ratios = {m: v.viirs_count/v.modis_count if v.modis_count else self.global_ratio for m, v in totals.iterrows()}
        self.state_ratios = {}
        if self.by_state:
            for key, v in frame.groupby(["state", "month"])[["modis_count", "viirs_count"]].sum().iterrows():
                self.state_ratios[key] = v.viirs_count/v.modis_count if v.modis_count else self.ratios[key[1]]
        return self

    def predict(self, frame):
        factors = [self.state_ratios.get((s, m), self.ratios.get(m, self.global_ratio)) for s, m in zip(frame.state, frame.month)]
        return frame.modis_count.to_numpy() * np.asarray(factors)


class CountGAM:
    """mu = seasonal_ratio * exp(spline + region correction) + softplus(region floor).

    NB2 variance = mu + alpha * mu**2. alpha=0 is the Poisson control.
    Input-dependent spline knots are learned on fitting data only. Corrections
    extrapolate constantly outside their learned support. Unseen regions receive
    zero deviation. No year or reference-sensor measurement is a predictor.
    """
    def __init__(self, penalty=.1, alpha=1., adapted=False):
        self.penalty, self.alpha, self.adapted = penalty, alpha, adapted

    def fit(self, frame):
        x = predictors(frame)
        self.ratio = SeasonalRatio(by_state=self.adapted).fit(frame)
        categories = ["month", "ecoregion"] + (["state"] if self.adapted else [])
        self.transform = ColumnTransformer([
            ("smooth", SplineTransformer(n_knots=3, degree=2, knots="quantile", include_bias=False, extrapolation="constant"), NUMERIC),
            ("regions", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categories),
        ])
        a = self.transform.fit_transform(x)
        self.scaler = StandardScaler(with_mean=False).fit(a)
        a = np.column_stack([np.ones(len(x)), self.scaler.transform(a)])
        self.floor_transform = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        z = np.column_stack([np.ones(len(x)), self.floor_transform.fit_transform(x[["ecoregion"]])])
        y, base = frame.viirs_count.to_numpy(), self.ratio.predict(frame)
        # Give California and the other four states equal combined weight for
        # the adapted fit. Plain pooling deliberately uses equal row weights.
        weight = np.ones(len(frame))
        if self.adapted:
            ca = frame.state.eq("CA").to_numpy()
            if ca.any() and (~ca).any():
                weight[ca] = .5 / ca.mean()
                weight[~ca] = .5 / (~ca).mean()
        n_a, n_z = a.shape[1], z.shape[1]
        initial = np.zeros(n_a + n_z)
        initial[n_a] = -3.
        penalty = np.full(len(initial), self.penalty)
        penalty[0] = self.penalty * .1
        penalty[n_a] = self.penalty * .1
        def objective(theta):
            eta = a @ theta[:n_a]
            # Bounds below and this smooth safety saturation avoid overflow.
            # Derivative includes saturation; there are no silently clipped gradients.
            bounded = 8 * np.tanh(eta / 8)
            signal = base * np.exp(bounded)
            floor_eta = z @ theta[n_a:]
            mu = signal + np.logaddexp(0, floor_eta) + 1e-9
            if self.alpha:
                r = 1 / self.alpha
                loss = (y+r)*np.log1p(mu/r) - y*np.log(mu) + y*np.log(r)
                dmu = (mu-y)/(mu*(1+self.alpha*mu))
            else:
                loss = mu-y*np.log(mu)
                dmu = 1-y/mu
            centered = theta-initial
            objective_value = np.mean(weight*loss) + .5*np.sum(penalty*centered**2)
            grad = np.r_[a.T @ (weight*dmu*signal*(1-np.tanh(eta/8)**2)),
                         z.T @ (weight*dmu*special.expit(floor_eta))] / len(y)
            return objective_value, grad+penalty*centered
        result = optimize.minimize(objective, initial, jac=True, method="L-BFGS-B",
            options={"maxiter": 700, "ftol": 1e-9, "gtol": 1e-5, "maxls": 40})
        self.optimization = {"success": bool(result.success), "iterations": int(result.nit),
                             "message": str(result.message), "gradient_max": float(np.abs(result.jac).max())}
        if not result.success:
            raise RuntimeError(f"GAM fit did not converge: {self.optimization}")
        self.coef, self.floor_coef = result.x[:n_a], result.x[n_a:]
        self.training_rows = len(frame)
        self.training_years = sorted(frame.year.unique().tolist())
        return self

    def predict(self, frame):
        x = predictors(frame)
        a = np.column_stack([np.ones(len(x)), self.scaler.transform(self.transform.transform(x))])
        z = np.column_stack([np.ones(len(x)), self.floor_transform.transform(x[["ecoregion"]])])
        return self.ratio.predict(frame)*np.exp(8*np.tanh((a@self.coef)/8)) + np.logaddexp(0, z@self.floor_coef)


class BoostedCorrection:
    def fit(self, frame):
        self.ratio = SeasonalRatio().fit(frame)
        base = self.ratio.predict(frame)
        self.features = NUMERIC + ["month_sin", "month_cos", "latitude", "longitude"]
        # Training sample weights turn fitting a count-per-baseline target into
        # Poisson fitting of counts with a log(base+.05) offset.
        exposure = base + .05
        self.model = HistGradientBoostingRegressor(loss="poisson", learning_rate=.035, max_iter=120,
            max_leaf_nodes=7, min_samples_leaf=100, l2_regularization=10, early_stopping=False, random_state=42)
        self.model.fit(predictors(frame)[self.features], frame.viirs_count / exposure, sample_weight=exposure)
        return self

    def predict(self, frame):
        return (self.ratio.predict(frame)+.05)*self.model.predict(predictors(frame)[self.features])


def metrics(frame, prediction):
    data = pd.DataFrame({"date": frame.date.to_numpy(), "actual": frame.viirs_count.to_numpy(), "predicted": prediction})
    monthly = data.groupby("date")[["actual", "predicted"]].sum()
    error = monthly.predicted-monthly.actual
    return {"monthly_mae": float(error.abs().mean()), "monthly_rmse": float(np.sqrt((error**2).mean())),
        "monthly_wape": float(error.abs().sum()/max(monthly.actual.sum(), 1)), "monthly_bias": float(error.mean()),
        "cell_month_mae": float((data.predicted-data.actual).abs().mean()),
        "n_months": len(monthly), "n_cell_months": len(frame)}


def make_model(name, penalty=.1):
    if name == "seasonal_ratio":
        return SeasonalRatio()
    if name == "boosted_correction_ca":
        return BoostedCorrection()
    return CountGAM(penalty=penalty, alpha=0 if name.startswith("poisson") else 1,
                    adapted=name.endswith("adapted"))


def fitting_rows(frame, name):
    return frame if "west" in name else frame[frame.state.eq("CA")]
