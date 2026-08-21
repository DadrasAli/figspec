# figspec

Render matplotlib figures from a declarative YAML spec, backed by CSV data.

Instead of writing plotting code, you describe the figure you want — series,
styling, axes, legend, output format — in a YAML file, and `figspec` renders
it. A config needs only a `series` list and an `output_basename`; every other
key has a sensible default.

```yaml
series:
  - csv: "data/accuracy.csv"
    column: "acc"
    label: "Client A"
output_basename: "out/accuracy"
```

```bash
figspec --config figure.yaml
```

## Features

- **Two series types**: `single` (one CSV column) and `combine` (several
  CSVs merged row-wise by a Python function, positional or keyword args)
- **Transforms**: inline `y_python`/`df_python` blocks, or reference a
  function in an external `.py` file with `y_transform: "file.py:fn"` —
  reusable across configs, real editor support
- **Error bands**: explicit `[lo, hi]` columns, `band_columns` (mean ± std
  across seed columns), or a symmetric spread column
- **Composite figures**: assemble a grid of panels from existing plot
  configs, with panel labels, a deduplicated global legend, and
  `series_overrides` that restyle every panel without touching the
  referenced files
- **Full styling control**: colors, line styles (named or custom dash
  patterns), markers, log axes, grids, dark backgrounds with automatic
  foreground contrast, LaTeX rendering, free-form text boxes
- **Validation**: unknown keys are rejected with a "did you mean" suggestion,
  not silently ignored; `--check` validates a config without rendering it
- **Output**: PNG/PDF/SVG/EPS/JPEG/TIFF, any subset, configurable DPI,
  overridable from the CLI (`-o`, `--dpi`, `--format`)

## Install

```bash
git clone git@github.com:DadrasAli/figspec.git
cd figspec
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

This installs a `figspec` command backed by matplotlib, numpy, pandas, and
PyYAML. Every command below assumes it's on your `PATH` (i.e. the venv above
is active).

## Usage

```bash
figspec --config figure.yaml                 # render
figspec --config figure.yaml --check         # validate without rendering
figspec --config figure.yaml -o out/name --dpi 150 --format svg --format pdf
```

A composite config (multiple panels assembled from other configs) is
detected automatically — same command, no separate flag.

## Examples

[`examples/`](examples/) has one config per feature above, each on a tiny
(5-6 row) CSV so the output is easy to verify by eye against the source data.

Run these from the repository root:

```bash
figspec --config examples/configs/01_minimal.yaml
```

Outputs land in `examples/out/`. Validate a config without rendering it:

```bash
figspec --config examples/configs/01_minimal.yaml --check
```

| # | Config | Demonstrates |
|---|---|---|
| 01 | [01_minimal.yaml](examples/configs/01_minimal.yaml) | Every key besides `series`/`output_basename` is optional |
| 02 | [02_style_and_markers.yaml](examples/configs/02_style_and_markers.yaml) | Per-series color, line style, marker, width, alpha, zorder, grid + minor grid |
| 03 | [03_dark_background.yaml](examples/configs/03_dark_background.yaml) | `background_color`; auto foreground contrast and auto-brightened colors |
| 04 | [04_log_and_axis_limits.yaml](examples/configs/04_log_and_axis_limits.yaml) | `y_log`, `y_axis_set: maxmin`, explicit `x_axis_set` |
| 05 | [05_x_column.yaml](examples/configs/05_x_column.yaml) | `x_column` — plot against a real, irregularly-spaced column instead of the row index |
| 06 | [06_transforms_inline.yaml](examples/configs/06_transforms_inline.yaml) | Inline `y_python` transform (EMA smoothing), raw vs. transformed side by side |
| 07 | [07_transforms_external.yaml](examples/configs/07_transforms_external.yaml) + [transforms.py](examples/transforms.py) | Same transform, defined in an external `.py` file and referenced as `y_transform: "file.py:function"` |
| 08 | [08_combine_positional.yaml](examples/configs/08_combine_positional.yaml) | `type: combine`, positional inputs, `align: min` |
| 09 | [09_combine_named.yaml](examples/configs/09_combine_named.yaml) | `combine`, named inputs (keyword args), `align: error` |
| 10 | [10_error_bands.yaml](examples/configs/10_error_bands.yaml) | Two band spellings on one figure: explicit `band: [lo, hi]` and `band_columns` (mean ± std) |
| 11 | [11_text_boxes.yaml](examples/configs/11_text_boxes.yaml) | `text_boxes`: a named anchor and an `[x, y]` position with a styled box |
| 12 | [12_outside_legend.yaml](examples/configs/12_outside_legend.yaml) | `legend_outside` + `legend_bbox` + `right_margin` |
| 13 | [13_composite.yaml](examples/configs/13_composite.yaml) (panels: [13a](examples/configs/13a_panel_accuracy.yaml), [13b](examples/configs/13b_panel_loss.yaml)) | Composite figure: panel labels, `series_overrides`, deduplicated `global_legend`, `global_title` |

Render every example at once:

```bash
for f in examples/configs/*.yaml; do figspec --config "$f"; done
```

### How paths inside a config resolve

This trips people up, so it's explicit here rather than left to be
discovered by a `FileNotFoundError`:

- **`csv:` data paths, `*_transform` file references, and a composite's
  panel `config:` references all resolve relative to the YAML file that
  contains them.** A config finds its data and its `transforms.py` no
  matter which directory you run `figspec` from.
- **`output_basename` is the one exception** — it resolves relative to the
  directory you *run the command from*, not to the config file (the same
  convention as `-o` in most CLI tools), so you control where results land.

That's why the example configs say `output_basename: "examples/out/..."` and
the commands above are run from the repository root. If you'd rather keep
your own configs runnable from anywhere, give `output_basename` an absolute
path, or override it per-run with `-o`:

```bash
figspec --config examples/configs/01_minimal.yaml -o /tmp/my_figure
```

## Testing

```bash
pip install -e ".[test]"
pytest
```

104 tests cover the config schema, rendering, external transforms, the CLI,
and composite figures — including regression tests for every bug found
during development.

## Security

`python`/`*_transform` blocks in a config execute with full Python
privileges — there is no sandbox, because `numpy`/`pandas` alone already
reach the filesystem. Treat a config file (and any `.py` file it references)
exactly like a script you are about to run: only render configs you trust.

## License

[MIT](LICENSE)
