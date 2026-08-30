"""Shared fixtures: an importable plotter module and small synthetic CSVs."""

import importlib.util
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: The only filled rows of sparse.csv's 'acc' column, as {row index: value}.
FILLED_ROWS = {
    0: 0.10, 2: 0.22, 5: 0.41, 6: 0.46,
    10: 0.58, 12: 0.65, 13: 0.67, 16: 0.74,
}

#: The 'round' values those rows sit at, in order.
FILLED_X = [1, 3, 6, 7, 11, 13, 14, 17]


@pytest.fixture(scope="session")
def plotter():
    """Import figspec.py by path so the tests need no packaging step."""
    spec = importlib.util.spec_from_file_location(
        "figspec", PROJECT_ROOT / "figspec.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def data_dir(tmp_path):
    """Write the CSVs every test draws from into an isolated directory."""
    steps = np.arange(1, 21)
    rng = np.random.default_rng(0)

    pd.DataFrame(
        {
            "round": steps,
            "acc": 1 - np.exp(-steps / 6),
            "loss": np.exp(-steps / 5),
        }
    ).to_csv(tmp_path / "a.csv", index=False)

    pd.DataFrame(
        {
            "round": steps,
            "acc": 1 - np.exp(-steps / 9),
            "loss": np.exp(-steps / 4),
        }
    ).to_csv(tmp_path / "b.csv", index=False)

    # A shorter file, for the align modes.
    pd.DataFrame({"round": steps[:12], "acc": np.linspace(0, 1, 12)}).to_csv(
        tmp_path / "short.csv", index=False
    )

    # Irregular x values plus per-seed columns, for x_column and bands.
    irregular = np.array([0, 5, 10, 20, 40, 80, 160, 320])
    base = 1 - np.exp(-irregular / 100)
    seeds = {
        f"seed{i}": base + rng.normal(0, 0.02, len(irregular)) for i in range(4)
    }
    frame = pd.DataFrame({"step": irregular, **seeds})
    frame["mean"] = frame[[f"seed{i}" for i in range(4)]].mean(axis=1)
    frame["std"] = frame[[f"seed{i}" for i in range(4)]].std(axis=1)
    frame["lo"] = frame["mean"] - frame["std"]
    frame["hi"] = frame["mean"] + frame["std"]
    frame.to_csv(tmp_path / "seeds.csv", index=False)

    # A gappy column: 20 rows with only 8 of them filled, including runs of
    # consecutive blanks -- the input 'skip_missing' exists for. 'lo'/'hi'
    # carry the same holes so a band can be trimmed alongside it, and
    # 'sparse_round' is an x column that is itself missing a value.
    gappy = np.full(20, np.nan)
    for index, value in FILLED_ROWS.items():
        gappy[index] = value
    sparse_round = steps.astype(float).copy()
    sparse_round[2] = np.nan

    pd.DataFrame(
        {
            "round": steps,
            "sparse_round": sparse_round,
            "acc": gappy,
            "lo": gappy - 0.05,
            "hi": gappy + 0.05,
            "empty": np.full(20, np.nan),
        }
    ).to_csv(tmp_path / "sparse.csv", index=False)

    return tmp_path


@pytest.fixture
def base_config(data_dir):
    """A minimal valid config; tests override only what they exercise."""
    return {
        "series": [
            {"csv": str(data_dir / "a.csv"), "column": "acc", "label": "A"}
        ],
        "output_basename": str(data_dir / "out" / "figure"),
    }
