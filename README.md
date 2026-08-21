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

See [`examples/`](examples/) for a numbered tour of every capability above,
each demonstrated on a tiny (5-6 row) CSV so the output is easy to verify by
eye.

## Install

```bash
git clone git@github.com:DadrasAli/figspec.git
cd figspec
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

This installs a `figspec` command backed by matplotlib, numpy, pandas, and
PyYAML.

## Usage

```bash
figspec --config figure.yaml                 # render
figspec --config figure.yaml --check         # validate without rendering
figspec --config figure.yaml -o out/name --dpi 150 --format svg --format pdf
```

A composite config (multiple panels assembled from other configs) is
detected automatically — same command, no separate flag.

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
