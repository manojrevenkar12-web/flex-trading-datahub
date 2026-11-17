"""A day-ahead forecast of the portfolio's net load from feat_load_qh: gradient-boosted trees on the features that
were known at the gate. The point is not the model but the data under it: the same model trained on features that
leak the future backtests well and forecasts worse in production."""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = ["local_hour", "weekday", "fc_temp_c", "fc_cloud", "fc_sun", "net_7d_mwh", "d2_net_known_mwh"]


def model():
    from lightgbm import LGBMRegressor
    return LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=20, subsample=0.9,
                         subsample_freq=1, colsample_bytree=0.9, random_state=0, verbose=-1, deterministic=True, n_jobs=1)


def split(df: pd.DataFrame, test_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.dropna(subset=["net_7d_mwh", "target_net_mwh"]).drop_duplicates("qh_start_utc").sort_values("qh_start_utc")
    days = sorted(df["delivery_day"].unique())
    cut = days[-test_days]
    return df[df["delivery_day"] < cut], df[df["delivery_day"] >= cut]


def fit_predict(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    m = model()
    m.fit(train[FEATURES], train["target_net_mwh"])
    return m.predict(test[FEATURES])
