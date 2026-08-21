# figspec

**Publication-quality figures from declarative YAML specifications.**

`figspec` separates the description of a figure from the code that draws it.
A specification declares what the figure contains — data sources, series,
transformations, axes, annotations, and output formats — and the renderer
produces it via matplotlib. Specifications are validated before rendering,
version-controllable alongside the data they describe, and reproducible
across runs.

Built for research workflows where figures are regenerated as results
evolve, and where a paper's figures should be reconstructible from source.

Specifications are plain YAML files, referred to below as configs — the term
used by the `--config` flag and the tool's own messages.

## Install

```bash
pipx install git+ssh://git@github.com/DadrasAli/figspec.git
```

This puts a `figspec` command on your `PATH` — available in every terminal
and every directory, with its dependencies (matplotlib, numpy, pandas,
PyYAML) isolated from the rest of your Python environment. No virtualenv to
activate.

If you don't have `pipx`: `python3 -m pip install --user pipx && python3 -m
pipx ensurepath`, then open a new terminal.

<details>
<summary>Alternative: plain <code>pip</code></summary>

```bash
pip install --user git+ssh://git@github.com/DadrasAli/figspec.git
```

Works, but installs the dependencies into your user environment rather than
an isolated one. `pipx` is preferred for command-line tools.
</details>

## Usage

Run `figspec` from wherever your data and configs live. A config needs only
a `series` list and an `output_basename`; every other key has a sensible
default.

```yaml
# figure.yaml
series:
  - csv: "data/accuracy.csv"
    column: "acc"
    label: "Client A"
output_basename: "out/accuracy"
```

```bash
figspec --config figure.yaml                 # render
figspec --config figure.yaml --check         # validate without rendering
figspec --config figure.yaml -o out/name --dpi 150 --format svg --format pdf
figspec --version                            # print the installed version
```

Paths behave the way a command-line tool should: everything is relative to
the directory you run from. Given this layout,

```
my-project/
├── csvs/
│   ├── accuracy.csv
│   └── figure.yaml     # output_basename: "out/accuracy"
```

running `figspec --config csvs/figure.yaml` from `my-project/` writes
`my-project/out/accuracy.png`. See
[How paths inside a config resolve](#how-paths-inside-a-config-resolve) for
the full rules.

A composite config (multiple panels assembled from other configs) is
detected automatically — same command, no separate flag.

## Examples

[`examples/`](examples/) has one config per feature, each on a tiny
(5-6 row) CSV so the output is easy to verify by eye against the source data.

**`pipx install` (above) does not include these.** It installs only the
`figspec` module — enough to run configs against your own data — not the
rest of the repository. The examples live in git; this pulls down just the
`examples/` directory, not the whole repository:

```bash
git clone --filter=blob:none --no-checkout --depth 1 --sparse \
    git@github.com:DadrasAli/figspec.git figspec-examples
cd figspec-examples
git sparse-checkout init --no-cone
git sparse-checkout set '/examples/*'
git checkout
```

Then, from `figspec-examples/`:

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

| Path | Resolved relative to |
|---|---|
| `--config` on the command line | the directory you run from |
| `output_basename` | the directory you run from |
| `csv:` data files | the config file first, then the directory you run from |
| `*_transform` `.py` references | the config file first, then the directory you run from |
| a composite's panel `config:` references | the config file first, then the directory you run from |

In short: **outputs land where you invoke the command**, and **inputs are
found whether you write them relative to the config or relative to where you
run**. A config that sits next to its data keeps working when called from a
parent directory, and `figspec --config csvs/figure.yaml` puts `out/` in the
current directory, not inside `csvs/`.

To pin outputs to a fixed location regardless of where the command runs, give
`output_basename` an absolute path, or override it per run:

```bash
figspec --config csvs/figure.yaml -o /data/figures/accuracy
```

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

## Security

`python`/`*_transform` blocks in a config execute with full Python
privileges — there is no sandbox, because `numpy`/`pandas` alone already
reach the filesystem. Treat a config file (and any `.py` file it references)
exactly like a script you are about to run: only render configs you trust.

## License

[MIT](LICENSE)
