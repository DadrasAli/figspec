"""Example external transform module, used by 07_transforms_external.yaml."""

import numpy as np


def smooth_ema(y, df, alpha=0.4):
    """Exponential moving average: out[i] = alpha*y[i] + (1-alpha)*out[i-1]."""
    out = np.empty_like(y, dtype=float)
    out[0] = y[0]
    for i in range(1, len(y)):
        out[i] = alpha * y[i] + (1 - alpha) * out[i - 1]
    return out


def keep_first_four(df):
    """A trivial dataframe transform: drop everything after round 4."""
    return df[df["round"] <= 4]
