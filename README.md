# figspec

## Publication-quality figures from declarative YAML specifications

`figspec` separates figure specification from rendering code. A config
defines the data sources, series, transformations, axes, annotations, and
output formats; the renderer validates the specification and generates the
figure with matplotlib.

It is designed for research workflows where figures are repeatedly
regenerated as results change and must remain reproducible from source.

## Install

```bash
pipx install git+ssh://git@github.com/DadrasAli/figspec.git
```

This puts a `figspec` command on your `PATH` — available in every terminal
and every directory, with its dependencies (matplotlib, numpy, pandas,
PyYAML) isolated from the rest of your Python environment. No virtualenv to
activate.

If you don't have `pipx` yet:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

Then open a new terminal (this step adds `pipx`'s install location to your
`PATH`, which only takes effect in shells started afterward).

## Usage

Run `figspec` from any directory you want. The minimal starter YAML file
looks like:

```yaml
# configs/config.yaml
series:
  - csv: "csvs/accuracy.csv"
    column: "acc"
    label: "Client A"
output_basename: "out/accuracy"
```

```bash
figspec --config configs/config.yaml                 # render
figspec --config configs/config.yaml --check          # validate without rendering
figspec --config configs/config.yaml --dpi 150 --format svg --format pdf
figspec --version                                     # print the installed version
```

Paths behave the way a command-line tool should: everything is relative to
the directory you run from. Given this layout,

```
my-project/
├── csvs/
│   └── accuracy.csv
├── configs/
│   └── config.yaml     # output_basename: "out/accuracy"
└── out/
    ├── accuracy.png
    └── accuracy.pdf
```

running the commands above from `my-project/` reads `csvs/accuracy.csv` and
writes `out/accuracy.png`/`.pdf` — `out/` didn't need to exist beforehand,
`figspec` creates it.

## Examples

[`examples/`](examples/) has one config per feature, each on a tiny
(5-6 row) CSV so the output is easy to verify by eye against the source data.

**`pipx install` (above) does not include these** — it installs only the
`figspec` module, not the rest of the repository. Download them separately:

```bash
git clone git@github.com:DadrasAli/figspec.git
cd figspec/examples
```

Then, from `examples/`:

```bash
figspec --config configs/01_minimal.yaml
```

Outputs land in `out/`.

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

## Developing figspec

The `pipx` install above is a frozen snapshot — edits to the source won't
affect it. To work on the code itself, use an editable install in a
virtualenv:

```bash
git clone git@github.com:DadrasAli/figspec.git
cd figspec
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
```

Inside that activated virtualenv, `figspec` runs your working copy, and
changes take effect immediately. Note that the virtualenv must be
re-activated (`source .venv/bin/activate`) in each new terminal.

### Testing

From that same virtualenv:

```bash
pytest
```

104 tests cover the config schema, rendering, external transforms, the CLI,
and composite figures — including regression tests for every bug found
during development.

## License

[MIT](LICENSE)
