"""End-to-end behaviour: the command line, output files and composites."""

import os

import pytest
import yaml


def write(path, cfg):
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return str(path)


@pytest.fixture
def config_file(tmp_path, base_config):
    return write(tmp_path / "figure.yaml", base_config)


# ----------------------------------------------------------------------
# Command line
# ----------------------------------------------------------------------

def test_a_minimal_config_renders_from_the_cli(plotter, config_file, data_dir):
    assert plotter.main(["--config", config_file]) == 0
    assert (data_dir / "out" / "figure.png").exists()
    assert (data_dir / "out" / "figure.pdf").exists()


def test_config_is_required(plotter):
    with pytest.raises(SystemExit):
        plotter.main([])


def test_a_missing_config_exits_non_zero(plotter, tmp_path):
    assert plotter.main(["--config", str(tmp_path / "nope.yaml")]) == 1


def test_a_typo_exits_non_zero(plotter, tmp_path, base_config):
    base_config["line_wdith"] = 3
    path = write(tmp_path / "bad.yaml", base_config)
    assert plotter.main(["--config", path]) == 1


def test_check_validates_without_writing_files(
    plotter, config_file, data_dir
):
    assert plotter.main(["--config", config_file, "--check"]) == 0
    assert not (data_dir / "out").exists()


def test_check_reports_an_invalid_config(plotter, tmp_path, base_config):
    base_config["series"] = []
    path = write(tmp_path / "bad.yaml", base_config)
    assert plotter.main(["--config", path, "--check"]) == 1


def test_output_flag_overrides_the_config(plotter, config_file, tmp_path):
    target = tmp_path / "elsewhere" / "renamed"
    assert plotter.main(["--config", config_file, "-o", str(target)]) == 0
    assert target.with_suffix(".png").exists()


def test_format_flag_overrides_the_config(plotter, config_file, data_dir):
    assert (
        plotter.main(
            ["--config", config_file, "--format", "svg", "--format", "pdf"]
        )
        == 0
    )
    out = data_dir / "out"
    assert (out / "figure.svg").exists()
    assert (out / "figure.pdf").exists()
    assert not (out / "figure.png").exists()


def test_an_unsupported_format_flag_exits_non_zero(plotter, config_file):
    assert plotter.main(["--config", config_file, "--format", "gif"]) == 1


def test_the_working_directory_is_not_polluted(plotter, tmp_path, monkeypatch):
    """A run used to create csv_plots/csv_configs/ in the caller's cwd."""
    workdir = tmp_path / "clean"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    plotter.main(["--config", str(tmp_path / "missing.yaml")])
    assert list(workdir.iterdir()) == []


# ----------------------------------------------------------------------
# Output files
# ----------------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["png", "pdf", "svg", "eps"])
def test_each_supported_format_is_written(
    plotter, base_config, data_dir, fmt
):
    base_config["formats"] = [fmt]
    base_config["output_basename"] = str(data_dir / "out" / "single")
    plotter.plot_from_config(base_config)
    assert (data_dir / "out" / f"single.{fmt}").exists()


def test_the_output_directory_is_created(plotter, base_config, data_dir):
    base_config["output_basename"] = str(data_dir / "deep" / "nested" / "fig")
    plotter.plot_from_config(base_config)
    assert (data_dir / "deep" / "nested" / "fig.png").exists()


# ----------------------------------------------------------------------
# Composites
# ----------------------------------------------------------------------

@pytest.fixture
def panels(tmp_path, data_dir):
    for name, column in (("p1", "acc"), ("p2", "loss")):
        write(
            tmp_path / f"{name}.yaml",
            {
                "series": [
                    {
                        "csv": str(data_dir / "a.csv"),
                        "column": column,
                        "label": f"{name} {column}",
                    }
                ],
                "title": name,
                "x_label": "Round",
                "y_label": column,
                "output_basename": str(data_dir / "out" / name),
            },
        )
    return tmp_path


def test_a_composite_renders_its_panels(plotter, panels, data_dir):
    path = write(
        panels / "composite.yaml",
        {
            "kind": "composite",
            "rows": 1,
            "columns": 2,
            "figures": [
                {"config": "p1.yaml", "label": "(a)"},
                {"config": "p2.yaml", "label": "(b)"},
            ],
            "global_title": "Both",
            "global_legend": True,
            "output_basename": str(data_dir / "out" / "composite"),
        },
    )
    assert plotter.main(["--config", path]) == 0
    assert (data_dir / "out" / "composite.png").exists()


@pytest.mark.parametrize("figsize", [(12, 3), (5, 8), (7, 4.5)])
def test_panel_captions_sit_below_the_axis_labels(plotter, figsize):
    """
    Captions used to use a fixed axes-relative offset, so they landed on top
    of the x label whenever the panel was short. They are now measured from
    the rendered bounding box, which has to hold at any aspect ratio.
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=figsize)
    try:
        ax.plot([1, 2, 3], [1, 2, 3])
        ax.set_xlabel("Round")
        fig.tight_layout()

        child_cfg = {"font_size_axes": 12, "background_color": "white"}
        plotter._draw_panel_labels(fig, [(ax, "(a)", {}, child_cfg)], {})

        renderer = fig.canvas.get_renderer()
        to_figure = fig.transFigure.inverted()
        caption = fig.texts[-1]

        caption_box = caption.get_window_extent(renderer).transformed(to_figure)
        label_box = (
            ax.xaxis.label.get_window_extent(renderer).transformed(to_figure)
        )

        assert caption.get_text() == "(a)"
        assert caption_box.y1 <= label_box.y0, (
            f"caption overlaps the x label at figsize={figsize}"
        )
    finally:
        plt.close(fig)


def test_an_explicit_panel_label_y_still_wins(plotter):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    try:
        ax.plot([1, 2], [1, 2])
        plotter._draw_panel_labels(
            fig,
            [(ax, "(a)", {"label_y": -0.5}, {"font_size_axes": 12})],
            {},
        )
        box = ax.get_position()
        assert fig.texts[-1].get_position()[1] == pytest.approx(
            box.y0 - 0.5 * box.height
        )
    finally:
        plt.close(fig)


def test_a_composite_rejects_an_unknown_key(plotter, panels, data_dir):
    path = write(
        panels / "composite.yaml",
        {
            "kind": "composite",
            "rows": 1,
            "columns": 2,
            "figures": [{"config": "p1.yaml"}],
            "gloabl_title": "typo",
            "output_basename": str(data_dir / "out" / "composite"),
        },
    )
    assert plotter.main(["--config", path]) == 1


def test_a_composite_reports_a_broken_panel_reference(
    plotter, panels, data_dir
):
    path = write(
        panels / "composite.yaml",
        {
            "kind": "composite",
            "rows": 1,
            "columns": 1,
            "figures": [{"config": "missing.yaml"}],
            "output_basename": str(data_dir / "out" / "composite"),
        },
    )
    assert plotter.main(["--config", path]) == 1


def test_series_overrides_do_not_touch_the_referenced_files(
    plotter, panels, data_dir
):
    original = (panels / "p1.yaml").read_text()
    path = write(
        panels / "composite.yaml",
        {
            "kind": "composite",
            "rows": 1,
            "columns": 2,
            "figures": [{"config": "p1.yaml"}, {"config": "p2.yaml"}],
            "series_overrides": {"line_width": 9, "color": "black"},
            "output_basename": str(data_dir / "out" / "composite"),
        },
    )
    assert plotter.main(["--config", path]) == 0
    assert (panels / "p1.yaml").read_text() == original


def test_local_feature_switches_are_respected(plotter, panels, data_dir):
    path = write(
        panels / "composite.yaml",
        {
            "kind": "composite",
            "rows": 2,
            "columns": 1,
            "figures": [{"config": "p1.yaml"}, {"config": "p2.yaml"}],
            "titles": False,
            "legends": False,
            "output_basename": str(data_dir / "out" / "composite"),
        },
    )
    assert plotter.main(["--config", path]) == 0


def test_explicit_panel_positions_are_honoured(plotter, panels, data_dir):
    path = write(
        panels / "composite.yaml",
        {
            "kind": "composite",
            "rows": 2,
            "columns": 2,
            "figures": [
                {"config": "p1.yaml", "position": [2, 2]},
                {"config": "p2.yaml", "position": [1, 1]},
            ],
            "output_basename": str(data_dir / "out" / "composite"),
        },
    )
    assert plotter.main(["--config", path]) == 0


def test_conflicting_panel_positions_are_rejected(plotter, panels, data_dir):
    path = write(
        panels / "composite.yaml",
        {
            "kind": "composite",
            "rows": 2,
            "columns": 2,
            "figures": [
                {"config": "p1.yaml", "position": [1, 1]},
                {"config": "p2.yaml", "position": [1, 1]},
            ],
            "output_basename": str(data_dir / "out" / "composite"),
        },
    )
    with pytest.raises(ValueError, match="both request"):
        plotter.main(["--config", path])


def test_more_panels_than_positions_is_rejected(plotter, panels, data_dir):
    path = write(
        panels / "composite.yaml",
        {
            "kind": "composite",
            "rows": 1,
            "columns": 1,
            "figures": [{"config": "p1.yaml"}, {"config": "p2.yaml"}],
            "output_basename": str(data_dir / "out" / "composite"),
        },
    )
    with pytest.raises(ValueError, match="positions"):
        plotter.main(["--config", path])


def test_nested_composites_are_rejected(plotter, panels, data_dir):
    write(
        panels / "inner.yaml",
        {"kind": "composite", "rows": 1, "columns": 1,
         "figures": [{"config": "p1.yaml"}],
         "output_basename": str(data_dir / "out" / "inner")},
    )
    path = write(
        panels / "outer.yaml",
        {"kind": "composite", "rows": 1, "columns": 1,
         "figures": [{"config": "inner.yaml"}],
         "output_basename": str(data_dir / "out" / "outer")},
    )
    with pytest.raises(ValueError, match="Nested"):
        plotter.main(["--config", path])
