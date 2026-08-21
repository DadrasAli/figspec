# Examples

Every config here uses the CSVs in `csv/` — 5-6 rows each, so you can open
the CSV next to the rendered figure and see exactly which number produced
which point. Run any one from this directory:

```bash
python ../csv_plotter.py --config configs/01_minimal.yaml
```

Outputs land in `out/`. Validate a config without rendering it:

```bash
python ../csv_plotter.py --config configs/01_minimal.yaml --check
```

## Index

| # | Config | Demonstrates |
|---|---|---|
| 01 | [01_minimal.yaml](configs/01_minimal.yaml) | Every key besides `series`/`output_basename` is optional |
| 02 | [02_style_and_markers.yaml](configs/02_style_and_markers.yaml) | Per-series color, line style, marker, width, alpha, zorder, grid + minor grid |
| 03 | [03_dark_background.yaml](configs/03_dark_background.yaml) | `background_color`; auto foreground contrast and auto-brightened colors |
| 04 | [04_log_and_axis_limits.yaml](configs/04_log_and_axis_limits.yaml) | `y_log`, `y_axis_set: maxmin`, explicit `x_axis_set` |
| 05 | [05_x_column.yaml](configs/05_x_column.yaml) | `x_column` — plot against a real, irregularly-spaced column instead of the row index |
| 06 | [06_transforms_inline.yaml](configs/06_transforms_inline.yaml) | Inline `y_python` transform (EMA smoothing), raw vs. transformed side by side |
| 07 | [07_transforms_external.yaml](configs/07_transforms_external.yaml) + [transforms.py](transforms.py) | Same transform, defined in an external `.py` file and referenced as `y_transform: "file.py:function"` |
| 08 | [08_combine_positional.yaml](configs/08_combine_positional.yaml) | `type: combine`, positional inputs, `align: min` |
| 09 | [09_combine_named.yaml](configs/09_combine_named.yaml) | `combine`, named inputs (keyword args), `align: error` |
| 10 | [10_error_bands.yaml](configs/10_error_bands.yaml) | Two band spellings on one figure: explicit `band: [lo, hi]` and `band_columns` (mean +/- std) |
| 11 | [11_text_boxes.yaml](configs/11_text_boxes.yaml) | `text_boxes`: a named anchor and an `[x, y]` position with a styled box |
| 12 | [12_outside_legend.yaml](configs/12_outside_legend.yaml) | `legend_outside` + `legend_bbox` + `right_margin` |
| 13 | [13_composite.yaml](configs/13_composite.yaml) (panels: [13a](configs/13a_panel_accuracy.yaml), [13b](configs/13b_panel_loss.yaml)) | Composite figure: panel labels, `series_overrides`, deduplicated `global_legend`, `global_title` |

Not covered by a dedicated config (they're CLI/output concerns, not YAML):

```bash
# override output path, dpi, and formats without editing the file
python ../csv_plotter.py --config configs/01_minimal.yaml -o out/custom --dpi 150 --format svg --format pdf

# render every config in a directory, with a key override applied to each
python ../csv_plotter_batch_run.py --config-dir configs --plotter ../csv_plotter.py --set dpi=150
```

## Two things worth knowing before you write your own

- **Paths inside a config resolve differently depending on what they point
  at.** `csv:`, `x_transform`/`y_transform`/etc. file refs, and a
  composite's panel `config:` refs all resolve relative to **the YAML file
  that contains them** — so a config still finds its data and its
  `transforms.py` no matter which directory you run the command from.
  `output_basename` is the one exception: it resolves relative to **the
  directory you run the command from** (the same convention as `-o` in most
  CLI tools), so you control where results land. That's why every config
  here writes `output_basename: "out/name"` — it assumes you're running
  from `examples/`, per the commands above. Running from `examples/configs/`
  instead would create `configs/out/` rather than reusing `examples/out/`.
- **A config's `python`/`_transform` code runs with full privileges** — no
  sandbox. Only render configs (and reference `.py` files) you trust, same
  as running any other script.
- **`--set` from the batch runner writes the same key into every config in
  the directory**, including composites. Composite configs accept a
  different key set than single-figure configs (no `line_width`, no
  `colors`, ...) — a key valid only on single figures will error on any
  composite config in that folder. `series_overrides` is the composite
  equivalent of a figure-level style key; `dpi` and `formats` are accepted
  by both, so they're the safe `--set` targets when a directory mixes both
  kinds of config (see `13_composite.yaml` for `series_overrides`).
