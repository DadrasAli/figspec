"""Defaults, aliases and validation of the YAML schema."""

import pytest


def test_minimal_config_only_needs_series_and_output(plotter, base_config):
    cfg = plotter.normalise_plot_config(base_config)
    assert cfg["title"] == ""
    assert cfg["figsize"] == [7.0, 4.5]
    assert cfg["formats"] == ["png", "pdf"]


def test_every_documented_default_is_filled_in(plotter, base_config):
    cfg = plotter.normalise_plot_config(base_config)
    missing = set(plotter.FIGURE_DEFAULTS) - set(cfg)
    assert not missing


def test_explicit_values_win_over_defaults(plotter, base_config):
    base_config["title"] = "Chosen"
    base_config["line_width"] = 4
    cfg = plotter.normalise_plot_config(base_config)
    assert cfg["title"] == "Chosen"
    assert cfg["line_width"] == 4


@pytest.mark.parametrize(
    "typo, suggestion",
    [
        ("line_wdith", "line_width"),
        ("titel", "title"),
        ("colours", "colors"),
        ("figsze", "figsize"),
    ],
)
def test_unknown_figure_key_is_rejected_with_a_suggestion(
    plotter, base_config, typo, suggestion
):
    base_config[typo] = 1
    with pytest.raises(plotter.ConfigError) as excinfo:
        plotter.normalise_plot_config(base_config)
    assert typo in str(excinfo.value)
    assert suggestion in str(excinfo.value)


def test_unknown_series_key_is_rejected(plotter, base_config):
    base_config["series"][0]["labl"] = "A"
    with pytest.raises(plotter.ConfigError, match="label"):
        plotter.normalise_plot_config(base_config)


@pytest.mark.parametrize(
    "alias, canonical",
    [
        ("linewidth", "line_width"),
        ("line_style", "line_styles"),
        ("fontsize_title", "font_size_title"),
        ("legend_ncol", "legend_columns"),
    ],
)
def test_aliases_resolve_to_canonical_names(
    plotter, base_config, alias, canonical
):
    base_config[alias] = 7
    cfg = plotter.normalise_plot_config(base_config)
    assert cfg[canonical] == 7
    assert alias not in cfg or alias == canonical


def test_alias_and_canonical_together_is_an_error(plotter, base_config):
    base_config["line_width"] = 2
    base_config["linewidth"] = 3
    with pytest.raises(plotter.ConfigError, match="use one"):
        plotter.normalise_plot_config(base_config)


def test_empty_series_is_rejected(plotter, base_config):
    base_config["series"] = []
    with pytest.raises(plotter.ConfigError, match="non-empty 'series'"):
        plotter.normalise_plot_config(base_config)


def test_single_series_requires_csv_and_column(plotter, base_config):
    del base_config["series"][0]["column"]
    with pytest.raises(plotter.ConfigError, match="missing 'column'"):
        plotter.normalise_plot_config(base_config)


def test_unsupported_output_format_is_rejected(plotter, base_config):
    base_config["formats"] = ["gif"]
    with pytest.raises(plotter.ConfigError, match="unsupported output format"):
        plotter.normalise_plot_config(base_config)


def test_unknown_composite_key_is_rejected(plotter):
    cfg = {"kind": "composite", "figures": ["a.yaml"], "gloabl_title": "x"}
    with pytest.raises(plotter.ConfigError, match="global_title"):
        plotter.normalise_composite_config(cfg)
