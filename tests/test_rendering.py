"""Rendering behaviour, including the regressions fixed in this file."""

import numpy as np
import pytest
from matplotlib import pyplot as plt


def render(plotter, cfg, **kwargs):
    """Render a config onto a throwaway axes and hand back the axes."""
    cfg = plotter.normalise_plot_config(cfg)
    fig, ax = plt.subplots()
    try:
        plotter._render_plot_on_axes(cfg, fig, ax, **kwargs)
        return fig, ax
    except Exception:
        plt.close(fig)
        raise


# ----------------------------------------------------------------------
# Regressions
# ----------------------------------------------------------------------

@pytest.mark.parametrize("use_grid", [True, False])
def test_legend_is_drawn_regardless_of_grid(plotter, base_config, use_grid):
    """The legend used to be nested inside the 'use_grid' branch."""
    base_config["use_grid"] = use_grid
    fig, ax = render(plotter, base_config)
    assert ax.get_legend() is not None
    plt.close(fig)


def test_show_legend_false_still_suppresses_the_legend(plotter, base_config):
    fig, ax = render(plotter, base_config, show_legend=False)
    assert ax.get_legend() is None
    plt.close(fig)


@pytest.mark.parametrize(
    "style", ["dashed", "dashdot", "dotted", "--", "-.", ":", "-"]
)
def test_named_line_styles_are_accepted(plotter, base_config, style):
    """Styles used to be passed as a positional format string."""
    base_config["series"][0]["line_style"] = style
    fig, ax = render(plotter, base_config)
    assert ax.lines[0].get_linestyle() is not None
    plt.close(fig)


def test_custom_dash_pattern_is_accepted(plotter, base_config):
    base_config["series"][0]["line_style"] = [0, [3, 1, 1, 1]]
    fig, ax = render(plotter, base_config)
    assert ax.lines[0].get_linestyle() is not None
    plt.close(fig)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("dashed", ["dashed"] * 3),
        ("--", ["--"] * 3),
        (["-", "--"], ["-", "--", "-"]),
        (None, ["-"] * 3),
    ],
)
def test_scalar_strings_are_not_indexed_per_character(
    plotter, value, expected
):
    """line_styles: 'dashed' used to become ['d', 'a', 's']."""
    assert plotter._get_styles(3, value) == expected


def test_scalar_colour_string_is_not_split(plotter):
    assert plotter._get_colors(2, "red") == ["red", "red"]


def test_dpi_is_honoured_for_single_figures(plotter, base_config, tmp_path):
    """dpi used to be hardcoded to 300 on this path."""
    from PIL import Image

    sizes = {}
    for dpi in (72, 200):
        base_config["dpi"] = dpi
        base_config["formats"] = ["png"]
        base_config["output_basename"] = str(tmp_path / f"fig{dpi}")
        plotter.plot_from_config(dict(base_config))
        sizes[dpi] = Image.open(tmp_path / f"fig{dpi}.png").size

    assert sizes[200][0] > sizes[72][0]


def test_rcparams_are_restored_after_rendering(plotter, base_config):
    """Font settings used to leak into the global rcParams."""
    before = (plt.rcParams["font.size"], plt.rcParams["text.usetex"])
    base_config["font_size_axes"] = 31
    plotter.plot_from_config(dict(base_config))
    assert (plt.rcParams["font.size"], plt.rcParams["text.usetex"]) == before


def test_a_failed_render_leaves_no_open_figure(plotter, base_config):
    base_config["series"][0]["csv"] = "does_not_exist.csv"
    before = len(plt.get_fignums())
    with pytest.raises(FileNotFoundError):
        plotter.plot_from_config(dict(base_config))
    assert len(plt.get_fignums()) == before


# ----------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------

def test_x_defaults_to_a_one_based_index(plotter, base_config):
    fig, ax = render(plotter, base_config)
    x = ax.lines[0].get_xdata()
    assert x[0] == 1
    plt.close(fig)


def test_x_column_is_used_when_given(plotter, base_config, data_dir):
    base_config["series"] = [
        {"csv": str(data_dir / "seeds.csv"), "column": "mean", "label": "m"}
    ]
    base_config["x_column"] = "step"
    fig, ax = render(plotter, base_config)
    assert list(ax.lines[0].get_xdata()[:4]) == [0, 5, 10, 20]
    plt.close(fig)


def test_missing_column_names_the_alternatives(plotter, base_config):
    base_config["series"][0]["column"] = "accuracy"
    with pytest.raises(plotter.ConfigError, match="Available"):
        render(plotter, base_config)


def test_missing_csv_is_reported_for_combine_inputs(
    plotter, base_config, data_dir
):
    base_config["series"] = [
        {
            "type": "combine",
            "label": "c",
            "inputs": [
                {"csv": "nope.csv", "column": "acc"},
                {"csv": str(data_dir / "b.csv"), "column": "acc"},
            ],
            "python": "def combine(a, b):\n    return a + b",
        }
    ]
    with pytest.raises(FileNotFoundError, match="nope.csv"):
        render(plotter, base_config)


def test_end_list_truncates_the_series(plotter, base_config):
    base_config["series"][0]["end"] = 5
    fig, ax = render(plotter, base_config)
    assert len(ax.lines[0].get_ydata()) == 5
    plt.close(fig)


# ----------------------------------------------------------------------
# Transforms
# ----------------------------------------------------------------------

def test_transforms_can_use_ordinary_builtins(plotter, base_config):
    """The old restricted-builtins dict broke sorted/zip/enumerate."""
    base_config["series"][0]["y_python"] = (
        "def transform_y(y, df):\n"
        "    return np.array(sorted(y, reverse=True))\n"
    )
    fig, ax = render(plotter, base_config)
    y = ax.lines[0].get_ydata()
    assert np.all(np.diff(y) <= 0)
    plt.close(fig)


def test_a_python_block_defining_the_wrong_name_is_reported(
    plotter, base_config
):
    base_config["series"][0]["y_python"] = "def nope(y, df):\n    return y\n"
    with pytest.raises(plotter.ConfigError, match="transform_y"):
        render(plotter, base_config)


def test_combine_supports_named_inputs(plotter, base_config, data_dir):
    base_config["series"] = [
        {
            "type": "combine",
            "label": "diff",
            "inputs": [
                {"name": "p", "csv": str(data_dir / "a.csv"), "column": "acc"},
                {"name": "q", "csv": str(data_dir / "b.csv"), "column": "acc"},
            ],
            "python": "def combine(p, q):\n    return p - q",
        }
    ]
    fig, ax = render(plotter, base_config)
    assert np.all(ax.lines[0].get_ydata() >= -1)
    plt.close(fig)


def test_align_min_trims_to_the_shorter_input(plotter, base_config, data_dir):
    base_config["series"] = [
        {
            "type": "combine",
            "label": "avg",
            "align": "min",
            "inputs": [
                {"csv": str(data_dir / "a.csv"), "column": "acc"},
                {"csv": str(data_dir / "short.csv"), "column": "acc"},
            ],
            "python": "def combine(a, b):\n    return 0.5 * (a + b)",
        }
    ]
    fig, ax = render(plotter, base_config)
    assert len(ax.lines[0].get_ydata()) == 12
    plt.close(fig)


def test_align_error_rejects_mismatched_lengths(
    plotter, base_config, data_dir
):
    base_config["series"] = [
        {
            "type": "combine",
            "label": "avg",
            "align": "error",
            "inputs": [
                {"csv": str(data_dir / "a.csv"), "column": "acc"},
                {"csv": str(data_dir / "short.csv"), "column": "acc"},
            ],
            "python": "def combine(a, b):\n    return 0.5 * (a + b)",
        }
    ]
    with pytest.raises(ValueError, match="mismatch"):
        render(plotter, base_config)


# ----------------------------------------------------------------------
# Bands and markers
# ----------------------------------------------------------------------

def test_explicit_band_columns_draw_a_filled_region(
    plotter, base_config, data_dir
):
    base_config["series"] = [
        {
            "csv": str(data_dir / "seeds.csv"),
            "column": "mean",
            "label": "m",
            "band": ["lo", "hi"],
        }
    ]
    fig, ax = render(plotter, base_config)
    assert len(ax.collections) == 1
    plt.close(fig)


def test_band_columns_produce_mean_plus_minus_std(
    plotter, base_config, data_dir
):
    base_config["series"] = [
        {
            "csv": str(data_dir / "seeds.csv"),
            "column": "mean",
            "label": "m",
            "band_columns": ["seed0", "seed1", "seed2", "seed3"],
        }
    ]
    fig, ax = render(plotter, base_config)
    assert len(ax.collections) == 1
    plt.close(fig)


def test_a_symmetric_band_uses_one_spread_column(
    plotter, base_config, data_dir
):
    base_config["series"] = [
        {
            "csv": str(data_dir / "seeds.csv"),
            "column": "mean",
            "label": "m",
            "band": "std",
        }
    ]
    fig, ax = render(plotter, base_config)
    assert len(ax.collections) == 1
    plt.close(fig)


def test_no_band_means_no_filled_region(plotter, base_config):
    fig, ax = render(plotter, base_config)
    assert not ax.collections
    plt.close(fig)


def test_markers_are_applied(plotter, base_config):
    base_config["series"][0]["marker"] = "o"
    fig, ax = render(plotter, base_config)
    assert ax.lines[0].get_marker() == "o"
    plt.close(fig)


def test_alpha_and_zorder_are_applied(plotter, base_config):
    base_config["series"][0]["alpha"] = 0.4
    base_config["series"][0]["zorder"] = 7
    fig, ax = render(plotter, base_config)
    assert ax.lines[0].get_alpha() == 0.4
    assert ax.lines[0].get_zorder() == 7
    plt.close(fig)


# ----------------------------------------------------------------------
# Axes
# ----------------------------------------------------------------------

def test_maxmin_fits_the_data_with_a_margin(plotter, base_config):
    base_config["y_axis_set"] = "maxmin"
    fig, ax = render(plotter, base_config)
    low, high = ax.get_ylim()
    y = ax.lines[0].get_ydata()
    assert low < y.min() and high > y.max()
    plt.close(fig)


def test_explicit_axis_limits_are_applied(plotter, base_config):
    base_config["y_axis_set"] = [0, 2]
    base_config["x_axis_set"] = [1, 10]
    fig, ax = render(plotter, base_config)
    assert ax.get_ylim() == (0, 2)
    assert ax.get_xlim() == (1, 10)
    plt.close(fig)


def test_an_invalid_axis_setting_is_reported(plotter, base_config):
    base_config["y_axis_set"] = "auto"
    with pytest.raises(plotter.ConfigError, match="y_axis_set"):
        render(plotter, base_config)


def test_log_scales_are_applied(plotter, base_config):
    base_config["x_log"] = True
    base_config["y_log"] = True
    fig, ax = render(plotter, base_config)
    assert ax.get_xscale() == "log" and ax.get_yscale() == "log"
    plt.close(fig)


def test_log_scales_can_be_suppressed_by_the_caller(plotter, base_config):
    base_config["y_log"] = True
    fig, ax = render(plotter, base_config, allow_y_log=False)
    assert ax.get_yscale() == "linear"
    plt.close(fig)


# ----------------------------------------------------------------------
# CSV path resolution (relative to the config's own directory)
# ----------------------------------------------------------------------

def test_relative_csv_path_resolves_against_config_dir(plotter, tmp_path):
    """
    A config referencing '../csv/x.csv' must resolve that path relative to
    the config file's own directory, not the process's working directory --
    the same convention already used for composite refs and transform files.
    """
    (tmp_path / "csv").mkdir()
    (tmp_path / "csv" / "a.csv").write_text("round,acc\n1,0.1\n2,0.2\n")
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()

    cfg = {
        "series": [{"csv": "../csv/a.csv", "column": "acc", "label": "A"}],
        "output_basename": str(tmp_path / "out" / "fig"),
    }
    cfg = plotter.normalise_plot_config(cfg)
    fig, ax = plt.subplots()
    try:
        plotter._render_plot_on_axes(cfg, fig, ax, config_dir=str(configs_dir))
        assert list(ax.lines[0].get_ydata()) == [0.1, 0.2]
    finally:
        plt.close(fig)


def test_relative_csv_path_is_not_found_via_cwd_alone(
    plotter, tmp_path, monkeypatch
):
    """A CSV that exists only next to the config must not be reachable
    purely because it happens to also exist relative to the CWD."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    cfg = {
        "series": [{"csv": "../csv/a.csv", "column": "acc", "label": "A"}],
        "output_basename": str(tmp_path / "out" / "fig"),
    }
    cfg = plotter.normalise_plot_config(cfg)
    fig, ax = plt.subplots()
    try:
        with pytest.raises(FileNotFoundError, match="a.csv"):
            plotter._render_plot_on_axes(
                cfg, fig, ax, config_dir=str(configs_dir)
            )
    finally:
        plt.close(fig)


def test_the_cli_resolves_csv_paths_relative_to_the_config_file(
    plotter, tmp_path, monkeypatch
):
    """
    End-to-end: a config referencing '../data.csv' must find it relative to
    the config file, even when invoked from an unrelated working directory.
    output_basename, by contrast, is resolved relative to that working
    directory (like -o in most CLI tools) -- both are asserted here so a
    future change can't quietly conflate the two conventions.
    """
    import yaml

    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "data.csv").write_text("round,acc\n1,0.5\n2,0.6\n")
    (sub / "fig.yaml").write_text(
        yaml.safe_dump(
            {
                "series": [
                    {"csv": "../data.csv", "column": "acc", "label": "A"}
                ],
                "output_basename": "out/fig",
            }
        )
    )

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert plotter.main(["--config", str(sub / "fig.yaml")]) == 0
    assert (elsewhere / "out" / "fig.png").exists()
    assert not (sub / "out").exists()
