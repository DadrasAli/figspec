"""External-file transform hooks: df_transform, y_transform, combine_transform,
band_transform, and their conflict/error/caching behaviour."""

import numpy as np
import pytest
import yaml


TRANSFORMS_PY = '''
import numpy as np

def double_it(y, df):
    return y * 2.0

def clip_low(df):
    df = df.copy()
    df["acc"] = df["acc"].clip(lower=0.5)
    return df

def mean_of(a, b):
    return 0.5 * (a + b)

def named_mean(p, q):
    return 0.5 * (p + q)

def spread_band(a, b):
    return np.minimum(a, b), np.maximum(a, b)
'''


@pytest.fixture
def transforms_file(tmp_path):
    path = tmp_path / "transforms.py"
    path.write_text(TRANSFORMS_PY)
    return path


def write(path, cfg):
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return str(path)


# ----------------------------------------------------------------------
# Direct-call tests (bypass the CLI; config_dir passed explicitly)
# ----------------------------------------------------------------------

def render(plotter, cfg, config_dir):
    import matplotlib.pyplot as plt

    cfg = plotter.normalise_plot_config(cfg)
    fig, ax = plt.subplots()
    try:
        plotter._render_plot_on_axes(cfg, fig, ax, config_dir=config_dir)
        return fig, ax
    except Exception:
        plt.close(fig)
        raise


def test_y_transform_loads_and_applies(
    plotter, base_config, transforms_file, data_dir
):
    raw = plotter._read_csv(str(data_dir / "a.csv"))["acc"].to_numpy()

    base_config["series"][0]["y_transform"] = "transforms.py:double_it"
    fig, ax = render(plotter, base_config, str(transforms_file.parent))
    y = ax.lines[0].get_ydata()

    import matplotlib.pyplot as plt
    plt.close(fig)
    assert np.allclose(y, raw * 2.0)


def test_df_transform_loads_and_applies(
    plotter, base_config, transforms_file, data_dir
):
    base_config["series"][0]["df_transform"] = "transforms.py:clip_low"
    fig, ax = render(plotter, base_config, str(transforms_file.parent))
    assert np.all(ax.lines[0].get_ydata() >= 0.5)
    import matplotlib.pyplot as plt
    plt.close(fig)


def test_combine_transform_positional(
    plotter, base_config, transforms_file, data_dir
):
    base_config["series"] = [
        {
            "type": "combine",
            "label": "m",
            "inputs": [
                {"csv": str(data_dir / "a.csv"), "column": "acc"},
                {"csv": str(data_dir / "b.csv"), "column": "acc"},
            ],
            "combine_transform": "transforms.py:mean_of",
        }
    ]
    fig, ax = render(plotter, base_config, str(transforms_file.parent))
    assert len(ax.lines[0].get_ydata()) > 0
    import matplotlib.pyplot as plt
    plt.close(fig)


def test_combine_transform_named(
    plotter, base_config, transforms_file, data_dir
):
    base_config["series"] = [
        {
            "type": "combine",
            "label": "m",
            "inputs": [
                {"name": "p", "csv": str(data_dir / "a.csv"), "column": "acc"},
                {"name": "q", "csv": str(data_dir / "b.csv"), "column": "acc"},
            ],
            "combine_transform": "transforms.py:named_mean",
        }
    ]
    fig, ax = render(plotter, base_config, str(transforms_file.parent))
    assert len(ax.lines[0].get_ydata()) > 0
    import matplotlib.pyplot as plt
    plt.close(fig)


def test_band_transform_on_combine(
    plotter, base_config, transforms_file, data_dir
):
    base_config["series"] = [
        {
            "type": "combine",
            "label": "m",
            "inputs": [
                {"csv": str(data_dir / "a.csv"), "column": "acc"},
                {"csv": str(data_dir / "b.csv"), "column": "acc"},
            ],
            "python": "def combine(a, b):\n    return 0.5 * (a + b)",
            "band": "std",
            "band_transform": "transforms.py:spread_band",
        }
    ]
    fig, ax = render(plotter, base_config, str(transforms_file.parent))
    assert len(ax.collections) == 1
    import matplotlib.pyplot as plt
    plt.close(fig)


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------

def test_missing_transform_file_is_reported(plotter, base_config, tmp_path):
    base_config["series"][0]["y_transform"] = "nope.py:foo"
    with pytest.raises(plotter.ConfigError, match="not found"):
        render(plotter, base_config, str(tmp_path))


def test_missing_function_suggests_a_close_match(
    plotter, base_config, transforms_file
):
    base_config["series"][0]["y_transform"] = "transforms.py:double_itt"
    with pytest.raises(plotter.ConfigError, match="double_it"):
        render(plotter, base_config, str(transforms_file.parent))


def test_malformed_reference_without_colon_is_rejected(
    plotter, base_config, transforms_file
):
    base_config["series"][0]["y_transform"] = "transforms.py"
    with pytest.raises(plotter.ConfigError, match="function_name"):
        render(plotter, base_config, str(transforms_file.parent))


def test_inline_and_external_together_is_rejected(
    plotter, base_config, transforms_file
):
    base_config["series"][0]["y_transform"] = "transforms.py:double_it"
    base_config["series"][0]["y_python"] = (
        "def transform_y(y, df):\n    return y\n"
    )
    with pytest.raises(plotter.ConfigError, match="use one"):
        render(plotter, base_config, str(transforms_file.parent))


def test_combine_requires_python_or_combine_transform(plotter, data_dir):
    cfg = {
        "series": [
            {
                "type": "combine",
                "label": "m",
                "inputs": [
                    {"csv": str(data_dir / "a.csv"), "column": "acc"},
                    {"csv": str(data_dir / "b.csv"), "column": "acc"},
                ],
            }
        ],
        "output_basename": str(data_dir / "out" / "x"),
    }
    with pytest.raises(plotter.ConfigError, match="combine_transform"):
        plotter.normalise_plot_config(cfg)


# ----------------------------------------------------------------------
# Path resolution: relative to the config file, not the CWD
# ----------------------------------------------------------------------

def test_relative_transform_path_resolves_against_config_dir(
    plotter, data_dir, monkeypatch, tmp_path
):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "transforms.py").write_text(
        "def double_it(y, df):\n    return y * 2.0\n"
    )
    cfg = {
        "series": [
            {
                "csv": str(data_dir / "a.csv"),
                "column": "acc",
                "label": "A",
                "y_transform": "transforms.py:double_it",
            }
        ],
        "output_basename": str(data_dir / "out" / "rel"),
    }
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    fig, ax = render(plotter, cfg, str(sub))
    assert np.all(ax.lines[0].get_ydata() > 0)
    import matplotlib.pyplot as plt
    plt.close(fig)


def test_relative_transform_path_not_found_via_cwd_alone(
    plotter, data_dir, monkeypatch, tmp_path
):
    """A transform file that exists only next to the config must not be
    reachable purely because it happens to also exist in the CWD."""
    sub = tmp_path / "sub"
    sub.mkdir()
    # Nothing written in tmp_path itself; only 'sub' has transforms.py.
    cfg = {
        "series": [
            {
                "csv": str(data_dir / "a.csv"),
                "column": "acc",
                "label": "A",
                "y_transform": "transforms.py:double_it",
            }
        ],
        "output_basename": str(data_dir / "out" / "rel2"),
    }
    monkeypatch.chdir(tmp_path)
    with pytest.raises(plotter.ConfigError, match="not found"):
        render(plotter, cfg, None)


# ----------------------------------------------------------------------
# Caching
# ----------------------------------------------------------------------

def test_the_same_file_is_imported_once(
    plotter, base_config, data_dir, tmp_path
):
    counter_file = tmp_path / "hits.txt"
    module_path = tmp_path / "counting.py"
    module_path.write_text(
        "with open(%r, 'a') as f:\n    f.write('x')\n\n"
        "def identity(y, df):\n    return y\n" % str(counter_file)
    )
    base_config["series"] = [
        {
            "csv": str(data_dir / "a.csv"),
            "column": "acc",
            "label": "A",
            "y_transform": "counting.py:identity",
        },
        {
            "csv": str(data_dir / "b.csv"),
            "column": "acc",
            "label": "B",
            "y_transform": "counting.py:identity",
        },
    ]
    fig, ax = render(plotter, base_config, str(tmp_path))
    import matplotlib.pyplot as plt
    plt.close(fig)
    assert counter_file.read_text() == "x"


# ----------------------------------------------------------------------
# CLI: --check catches a broken reference without rendering, composites
# resolve each panel's transform relative to that panel's own file
# ----------------------------------------------------------------------

def test_check_catches_a_broken_external_reference(
    plotter, base_config, transforms_file, tmp_path
):
    base_config["series"][0]["y_transform"] = "transforms.py:nope_fn"
    path = write(tmp_path / "figure.yaml", base_config)
    assert plotter.main(["--config", path, "--check"]) == 1


def test_check_passes_a_valid_external_reference(
    plotter, base_config, transforms_file, tmp_path, data_dir
):
    base_config["series"][0]["y_transform"] = "transforms.py:double_it"
    path = write(tmp_path / "figure.yaml", base_config)
    assert plotter.main(["--config", path, "--check"]) == 0
    assert not (data_dir / "out").exists()


def test_composite_panels_resolve_transforms_relative_to_their_own_file(
    plotter, data_dir, tmp_path
):
    panel_a = tmp_path / "a"
    panel_b = tmp_path / "b"
    panel_a.mkdir()
    panel_b.mkdir()
    (panel_a / "transforms.py").write_text(
        "def bump(y, df):\n    return y + 100.0\n"
    )
    (panel_b / "transforms.py").write_text(
        "def bump(y, df):\n    return y - 100.0\n"
    )
    write(
        panel_a / "p.yaml",
        {
            "series": [
                {
                    "csv": str(data_dir / "a.csv"),
                    "column": "acc",
                    "label": "A",
                    "y_transform": "transforms.py:bump",
                }
            ],
            "output_basename": str(data_dir / "out" / "panelA"),
        },
    )
    write(
        panel_b / "p.yaml",
        {
            "series": [
                {
                    "csv": str(data_dir / "a.csv"),
                    "column": "acc",
                    "label": "A",
                    "y_transform": "transforms.py:bump",
                }
            ],
            "output_basename": str(data_dir / "out" / "panelB"),
        },
    )
    composite_path = write(
        tmp_path / "composite.yaml",
        {
            "kind": "composite",
            "rows": 1,
            "columns": 2,
            "figures": [
                {"config": str(panel_a / "p.yaml")},
                {"config": str(panel_b / "p.yaml")},
            ],
            "output_basename": str(data_dir / "out" / "composite"),
        },
    )
    assert plotter.main(["--config", composite_path]) == 0
    assert (data_dir / "out" / "composite.png").exists()
