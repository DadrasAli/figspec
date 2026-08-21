#!/usr/bin/env python3
"""
figspec: render figures from a declarative YAML spec, backed by pandas/CSV
data and matplotlib.

A config needs only a 'series' list and an 'output_basename'; every other
key has a default. Supported series:

  single    one column of one CSV, with optional pandas/numpy transforms
  combine   several CSVs merged row-wise by a user-defined Python function

Figures can also be assembled into multi-panel composites from existing
plot configs.

  figspec.py --config figure.yaml
  figspec.py --config composite.yaml
  figspec.py --config figure.yaml --check
  figspec.py --config figure.yaml -o out/final --format pdf --dpi 600

SECURITY: 'python' blocks in a config are executed with full privileges.
Treat a config like a script you are about to run.
"""

import os
import sys
import copy
import difflib
import argparse
import importlib.util
from pathlib import Path

import yaml
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import colors as mcolors
from matplotlib.ticker import AutoMinorLocator
import textwrap

#: Output formats _save_figure() knows how to write.
SUPPORTED_FORMATS = {"png", "pdf", "svg", "eps", "jpg", "jpeg", "tif", "tiff"}

#: Imported transform modules, keyed by resolved absolute path, so a file
#: referenced by several series (or several times across a composite) is
#: only imported once per process.
_EXTERNAL_MODULE_CACHE = {}

# ============================================================
# Configuration schema: defaults, aliases and validation
# ============================================================

#: Figure-level defaults. A config only has to name what it wants to change,
#: so the minimum viable plot config is a 'series' list plus 'output_basename'.
FIGURE_DEFAULTS = {
    "title": "",
    "x_label": "",
    "y_label": "",
    "x_log": False,
    "y_log": False,
    "y_axis_set": None,
    "x_axis_set": None,
    "use_grid": False,
    "grid_style": ":",
    "grid_alpha": 0.3,
    "minor_grid": False,
    "minor_grid_style": ":",
    "minor_grid_alpha": 0.3,
    "minor_grid_divisions": 5,
    "figsize": [7.0, 4.5],
    "dpi": 300,
    "formats": ["png", "pdf"],
    "background_color": "white",
    "colors": None,
    "line_styles": None,
    "line_width": 2.0,
    "markers": None,
    "marker_size": 6.0,
    "marker_every": None,
    "alpha": 1.0,
    "font_size_title": 16,
    "font_size_axes": 13,
    "font_size_legends": 11,
    "legend_outside": False,
    "legend_loc": None,
    "legend_columns": 1,
    "legend_bbox": None,
    "legend_frame": True,
    "show_legend": True,
    "right_margin": 0.75,
    "use_tex": False,
    "x_column": None,
    "end_list_global": None,
    "text_boxes": [],
}

#: Alternative spellings accepted for figure-level keys, mapped to the
#: canonical name that the renderer actually reads.
FIGURE_ALIASES = {
    "linewidth": "line_width",
    "line_style": "line_styles",
    "color": "colors",
    "marker": "markers",
    "markersize": "marker_size",
    "markevery": "marker_every",
    "fontsize_title": "font_size_title",
    "fontsize_axes": "font_size_axes",
    "fontsize_legends": "font_size_legends",
    "font_size_legend": "font_size_legends",
    "grid": "use_grid",
    "output": "output_basename",
    "legend_ncol": "legend_columns",
}

#: Keys a config may contain that are not covered by FIGURE_DEFAULTS.
FIGURE_EXTRA_KEYS = {
    "series",
    "output_basename",
    "latex_preamble",
    "legend_facecolor",
    "legend_edgecolor",
    "kind",
}

#: Keys accepted inside one entry of the 'series' list.
SERIES_KEYS = {
    "type", "label", "csv", "column", "x_column",
    "end", "end_list",
    "color", "line_style", "line_styles", "line_width",
    "marker", "markers", "marker_size", "marker_every",
    "alpha", "zorder", "legend_color",
    "df_python", "df_fn", "df_transform",
    "y_python", "y_fn", "y_transform",
    "inputs", "python", "fn", "combine_transform", "align",
    "band", "band_alpha", "band_color", "band_columns",
    "band_python", "band_fn", "band_transform", "band_inputs",
}

#: Keys accepted inside one entry of a combine series' 'inputs' list.
INPUT_KEYS = {"name", "csv", "column", "x_column"}

#: Keys accepted inside one entry of the 'text_boxes' list.
TEXT_BOX_KEYS = {
    "text", "position", "offset", "text_align", "box",
    "horizontal_align", "vertical_align", "font_size", "text_color",
    "font_weight", "font_style", "rotation", "zorder", "clip_on",
}

#: Keys accepted by a composite config, in addition to FIGURE_EXTRA_KEYS.
COMPOSITE_KEYS = {
    "kind", "type", "rows", "columns", "figures", "figsize", "dpi",
    "formats", "output_basename", "background_color", "series_overrides",
    "titles", "legends", "x_labels", "y_labels", "x_logs", "y_logs",
    "local_titles", "local_legends", "local_x_labels", "local_y_labels",
    "local_x_logs", "local_y_logs",
    "global_title", "global_x_label", "global_y_label",
    "global_title_color", "global_title_y",
    "global_x_label_color", "global_x_label_x", "global_x_label_y",
    "global_y_label_color", "global_y_label_x", "global_y_label_y",
    "global_foreground_color",
    "font_size_global_title", "font_size_global_axes",
    "font_size_panel_labels", "font_size_legends",
    "global_legend", "legend_loc", "legend_bbox", "legend_columns",
    "legend_outside", "legend_facecolor", "legend_edgecolor",
    "panel_label_color", "panel_label_font_weight", "panel_label_y",
    "panel_label_pad",
    "tight_layout", "layout_padding",
    "left_margin", "right_margin", "top_margin", "bottom_margin",
    "horizontal_padding", "vertical_padding",
    "horizontal_spacing", "vertical_spacing",
    "use_tex", "latex_preamble",
}

#: Keys accepted on one entry of a composite 'figures' list.
FIGURE_ENTRY_KEYS = {
    "config", "label", "position", "location",
    "label_y", "label_pad", "label_color", "label_font_size",
    "label_font_weight",
}


class ConfigError(ValueError):
    """Raised when a YAML config cannot be understood."""


def _suggest(key, known):
    match = difflib.get_close_matches(str(key), sorted(known), n=1, cutoff=0.6)
    return f" Did you mean '{match[0]}'?" if match else ""


def _reject_unknown_keys(mapping, known, where):
    """Fail loudly on a key the renderer would otherwise ignore silently."""
    if not isinstance(mapping, dict):
        raise ConfigError(f"{where} must be a mapping.")
    for key in mapping:
        if key not in known:
            raise ConfigError(
                f"Unknown key '{key}' in {where}.{_suggest(key, known)}"
            )


def _resolve_aliases(cfg, aliases, where):
    """Rewrite accepted alternative spellings to their canonical names."""
    resolved = {}
    for key, value in cfg.items():
        canonical = aliases.get(key, key)
        if canonical in resolved:
            raise ConfigError(
                f"{where} sets both '{key}' and '{canonical}'; use one."
            )
        resolved[canonical] = value
    return resolved


def normalise_plot_config(cfg, where="config"):
    """
    Validate one normal plot config and fill in every default.

    After this call the renderer can read canonical keys directly, and any
    key the renderer does not understand has already been reported.
    """
    if not isinstance(cfg, dict):
        raise ConfigError(f"{where} must be a mapping.")

    cfg = _resolve_aliases(cfg, FIGURE_ALIASES, where)
    known = set(FIGURE_DEFAULTS) | FIGURE_EXTRA_KEYS
    _reject_unknown_keys(cfg, known, where)

    series = cfg.get("series")
    if not isinstance(series, list) or not series:
        raise ConfigError(f"{where} requires a non-empty 'series' list.")

    resolved = dict(FIGURE_DEFAULTS)
    resolved.update(cfg)

    resolved["series"] = [
        _normalise_series(spec, index, where)
        for index, spec in enumerate(series)
    ]

    for index, spec in enumerate(resolved["text_boxes"] or []):
        _reject_unknown_keys(spec, TEXT_BOX_KEYS, f"{where} text_boxes[{index}]")

    formats = _as_cycle(resolved["formats"])
    unsupported = [f for f in formats if f.lower() not in SUPPORTED_FORMATS]
    if unsupported:
        raise ConfigError(
            f"{where} requests unsupported output format(s) "
            f"{unsupported}. Supported: {sorted(SUPPORTED_FORMATS)}."
        )
    resolved["formats"] = [f.lower() for f in formats]

    return resolved


def _normalise_series(spec, index, where):
    label = f"{where} series[{index}]"
    if not isinstance(spec, dict):
        raise ConfigError(f"{label} must be a mapping.")
    _reject_unknown_keys(spec, SERIES_KEYS, label)

    stype = spec.get("type", "single")
    if stype not in {"single", "combine"}:
        raise ConfigError(
            f"{label} has unknown type '{stype}'. Use 'single' or 'combine'."
        )

    if stype == "single":
        for required in ("csv", "column"):
            if required not in spec:
                raise ConfigError(f"{label} is missing '{required}'.")
    else:
        inputs = spec.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            raise ConfigError(f"{label} requires a non-empty 'inputs' list.")
        for j, inp in enumerate(inputs):
            _reject_unknown_keys(inp, INPUT_KEYS, f"{label} inputs[{j}]")
            for required in ("csv", "column"):
                if required not in inp:
                    raise ConfigError(
                        f"{label} inputs[{j}] is missing '{required}'."
                    )
        if "python" not in spec and "combine_transform" not in spec:
            raise ConfigError(
                f"{label} requires a 'python' block or 'combine_transform'."
            )

    return spec


def normalise_composite_config(cfg, where="composite config"):
    """Validate a composite config and reject keys it would silently ignore."""
    if not isinstance(cfg, dict):
        raise ConfigError(f"{where} must be a mapping.")
    _reject_unknown_keys(cfg, COMPOSITE_KEYS, where)

    figures = cfg.get("figures")
    if not isinstance(figures, list) or not figures:
        raise ConfigError(f"{where} requires a non-empty 'figures' list.")
    for index, entry in enumerate(figures):
        if isinstance(entry, dict):
            _reject_unknown_keys(
                entry, FIGURE_ENTRY_KEYS, f"{where} figures[{index}]"
            )
    return cfg


# ============================================================
# Helper utilities
# ============================================================

def _is_dark(color):
    r, g, b, _ = mcolors.to_rgba(color)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return lum < 0.5


def _brighten(rgba, amount=0.35):
    r, g, b, a = rgba
    r = r + (1 - r) * amount
    g = g + (1 - g) * amount
    b = b + (1 - b) * amount
    return (r, g, b, a)


def _auto_colors_for_background(n, bg_color):
    cmap = plt.get_cmap("tab10")
    base = [cmap(i % 10) for i in range(n)]
    if _is_dark(bg_color):
        return [_brighten(c, 0.35) for c in base]
    return base


def _get_colors(n, user_colors, background_color="white"):
    user_colors = _as_cycle(user_colors)
    if not user_colors:
        return _auto_colors_for_background(n, background_color)
    return [user_colors[i % len(user_colors)] for i in range(n)]


def _apply_foreground_contrast(ax, bg_color):
    fg = "white" if _is_dark(bg_color) else "black"

    ax.tick_params(colors=fg, which="both")
    ax.xaxis.label.set_color(fg)
    ax.yaxis.label.set_color(fg)
    ax.title.set_color(fg)

    for spine in ax.spines.values():
        spine.set_color(fg)

    # If grid is enabled, make it visible too
    for gl in ax.get_xgridlines() + ax.get_ygridlines():
        gl.set_color(fg)

    leg = ax.get_legend()
    if leg is not None:
        frame = leg.get_frame()
        frame.set_facecolor(bg_color)
        frame.set_edgecolor(fg)
        leg.get_title().set_color(fg)
        for t in leg.get_texts():
            t.set_color(fg)


def _is_dash_pattern(value):
    """
    Detect a Matplotlib dash specification such as [0, [3, 1, 1, 1]].

    In YAML this arrives as a two-element list whose second element is itself
    a list, which must be treated as one style rather than a style cycle.
    """
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (list, tuple))
    )


def _as_cycle(value):
    """
    Normalise a YAML scalar-or-list into a list.

    A bare string such as line_styles: "--" is one style, not a sequence of
    characters, so it must not be indexed element-wise.
    """
    if value is None:
        return None
    if isinstance(value, (str, bytes)):
        return [value]
    if _is_dash_pattern(value):
        return [(value[0], tuple(value[1]))]
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _get_styles(n, style_list):
    style_list = _as_cycle(style_list)
    if not style_list:
        return ["-"] * n
    return [style_list[i % len(style_list)] for i in range(n)]


def _compile_function(code: str, fn_name: str):
    """
    Compile a user-defined Python function taken from a YAML config.

    SECURITY: a config's python blocks are executed with the full Python
    builtins and the same privileges as this process. There is no sandbox and
    none is attempted, because numpy and pandas alone already reach the
    filesystem. Treat a config file exactly like a script you are about to
    run: only render configs you trust.

    The block is given 'np' and 'pd' for convenience.
    """
    if not code:
        return None

    env = {"__builtins__": __builtins__, "np": np, "pd": pd}
    loc = {}

    try:
        exec(textwrap.dedent(code), env, loc)
    except Exception as exc:
        raise ConfigError(
            f"Failed to execute the python block defining '{fn_name}': {exc}"
        ) from exc

    fn = loc.get(fn_name)
    if fn is None or not callable(fn):
        defined = ", ".join(sorted(k for k in loc if not k.startswith("_")))
        raise ConfigError(
            f"The python block must define a callable named '{fn_name}'. "
            f"Defined instead: {defined or 'nothing'}."
        )
    return fn


def _find_referenced_file(raw_path, base_dir):
    """
    Look up a path referenced from a config: relative to base_dir (the
    referencing config's own directory) first, then the working directory.
    This is the one convention used everywhere a config points at another
    file -- composite panels, transform files, and CSVs alike -- so a config
    works the same way regardless of the directory it is run from.

    Returns (resolved_path, candidates_tried). resolved_path is None if none
    of the candidates exist, so the caller can raise its own error type.
    """
    path = Path(os.path.expandvars(str(raw_path))).expanduser()
    if path.is_absolute():
        candidates = [path]
    else:
        candidates = []
        if base_dir is not None:
            candidates.append(Path(base_dir) / path)
        candidates.append(Path.cwd() / path)

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve(), candidates
    return None, candidates


def _resolve_transform_path(raw_path, base_dir):
    """Resolve a transform file path relative to its config's directory."""
    resolved, candidates = _find_referenced_file(raw_path, base_dir)
    if resolved is None:
        attempted = ", ".join(str(c) for c in candidates)
        raise ConfigError(f"Transform file not found: {raw_path}. Tried: {attempted}")
    return resolved


def _load_external_module(path):
    """Import a transform file once per process and cache the module."""
    key = str(path)
    module = _EXTERNAL_MODULE_CACHE.get(key)
    if module is not None:
        return module

    module_name = f"figspec_transforms_{abs(hash(key))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ConfigError(f"Failed to import {path}: {exc}") from exc

    _EXTERNAL_MODULE_CACHE[key] = module
    return module


def _load_external_function(spec_value, base_dir, hook_name):
    """
    Load a function from an external Python file.

    SECURITY: same as _compile_function -- the file executes with full
    privileges. Only reference transform files you trust.

    Syntax: "path/to/file.py:function_name", the path resolved relative to
    the YAML config that references it (like a composite's panel configs).
    """
    if not isinstance(spec_value, str) or spec_value.count(":") == 0:
        raise ConfigError(
            f"'{hook_name}' must be \"path/to/file.py:function_name\"; "
            f"got {spec_value!r}."
        )

    file_part, _, func_name = spec_value.rpartition(":")
    if not file_part or not func_name.isidentifier():
        raise ConfigError(
            f"'{hook_name}' must be \"path/to/file.py:function_name\"; "
            f"got {spec_value!r}."
        )

    path = _resolve_transform_path(file_part, base_dir)
    module = _load_external_module(path)

    fn = getattr(module, func_name, None)
    if fn is None or not callable(fn):
        available = sorted(
            name for name in vars(module)
            if callable(getattr(module, name)) and not name.startswith("_")
        )
        raise ConfigError(
            f"'{hook_name}': {path} has no callable '{func_name}'."
            f"{_suggest(func_name, available)} "
            f"Defined: {', '.join(available) or 'nothing'}."
        )
    return fn


def _resolve_hook(spec, *, inline_key, fn_key, external_key, default_fn,
                   config_dir, hook_label):
    """
    Return the callable for one transform hook, or None if unset.

    A hook can be defined inline ('<x>_python' + optional '<x>_fn') or as a
    reference into an external file ('<x>_transform'); setting both is an
    error rather than a silent pick.
    """
    has_inline = inline_key in spec
    has_external = external_key in spec

    if has_inline and has_external:
        raise ConfigError(
            f"{hook_label} sets both '{inline_key}' and '{external_key}'; "
            "use one."
        )
    if has_external:
        return _load_external_function(spec[external_key], config_dir, external_key)
    if has_inline:
        return _compile_function(spec[inline_key], spec.get(fn_key, default_fn))
    return None


def _apply_axis_limits(ax, axis, setting, all_values):
    """
    Apply an axis limit setting.

    None            leave Matplotlib's autoscaling alone
    "maxmin"        fit the data with a 5% margin (y axis only)
    [low, high]     explicit limits, either end may be null to autoscale
    """
    if setting is None:
        return

    setter = ax.set_ylim if axis == "y" else ax.set_xlim

    if setting == "maxmin":
        if all_values is None or not len(all_values):
            return
        vals = np.concatenate([np.asarray(a, dtype=float) for a in all_values])
        vals = vals[np.isfinite(vals)]
        if not vals.size:
            return
        low, high = float(vals.min()), float(vals.max())
        margin = 0.05 * (high - low) if high > low else max(abs(high), 1.0) * 0.05
        setter(low - margin, high + margin)
        return

    if isinstance(setting, (list, tuple)) and len(setting) == 2:
        setter(setting[0], setting[1])
        return

    raise ConfigError(
        f"'{axis}_axis_set' must be null, \"maxmin\", or [low, high]; "
        f"got {setting!r}."
    )


def _get_markers(n, marker_list):
    marker_list = _as_cycle(marker_list)
    if not marker_list:
        return [None] * n
    return [marker_list[i % len(marker_list)] for i in range(n)]


def _read_csv(path, end=None, config_dir=None):
    """
    Read a CSV with a clear error, optionally truncated to 'end' rows.

    'path' resolves relative to config_dir (the directory of the config that
    referenced it) first, then the working directory -- the same convention
    already used for composite panel refs and transform files, so a config
    behaves the same regardless of where it is run from.
    """
    resolved, candidates = _find_referenced_file(path, config_dir)
    if resolved is None:
        attempted = ", ".join(str(c) for c in candidates)
        raise FileNotFoundError(f"CSV not found: {path}. Tried: {attempted}")
    df = pd.read_csv(resolved)
    if end is not None:
        df = df.iloc[:end]
    return df


def _column(df, name, path):
    """Fetch one column, naming the alternatives when it is missing."""
    if name not in df.columns:
        available = ", ".join(map(str, df.columns))
        raise ConfigError(
            f"Column '{name}' not found in {path}."
            f"{_suggest(name, df.columns)} Available: {available}."
        )
    return df[name].to_numpy()


def _resolve_band(spec, df, path, y, config_dir, hook_label):
    """
    Build the lower/upper edges of a shaded band for a 'single' series.

    Two spellings are supported:
      band: [lower_column, upper_column]   explicit bounds
      band: spread_column                  symmetric y +/- spread
      band_columns: [seed1, seed2, ...]    mean +/- standard deviation
    """
    if "band_columns" in spec:
        columns = _as_cycle(spec["band_columns"])
        stacked = np.vstack([_column(df, c, path) for c in columns])
        spread = stacked.std(axis=0)
        centre = stacked.mean(axis=0)
        return centre - spread, centre + spread

    if "band" not in spec:
        return None, None

    band = spec["band"]
    if isinstance(band, (list, tuple)) and len(band) == 2:
        return _column(df, band[0], path), _column(df, band[1], path)

    spread = _column(df, band, path)
    fn = _resolve_hook(
        spec,
        inline_key="band_python",
        fn_key="band_fn",
        external_key="band_transform",
        default_fn="transform_band",
        config_dir=config_dir,
        hook_label=hook_label,
    )
    if fn is not None:
        spread = np.asarray(fn(spread, df))
    y, spread = _align_arrays([np.asarray(y), np.asarray(spread)], "min")
    return y - spread, y + spread


def _resolve_combine_band(spec, ys, y, align, config_dir, hook_label):
    """
    Build a band for a 'combine' series.

    band: spread across the combined inputs (mean +/- std of the inputs)
    band: [lower_expr, upper_expr] is not supported here; use band_python
    or band_transform with the combined inputs instead.
    """
    band = spec.get("band")
    if band is None:
        return None, None

    if band in ("std", "spread", True):
        stacked = np.vstack(_align_arrays([np.asarray(a) for a in ys], align))
        spread = stacked.std(axis=0)
        centre = np.asarray(y)
        centre, spread = _align_arrays([centre, spread], "min")
        return centre - spread, centre + spread

    fn = _resolve_hook(
        spec,
        inline_key="band_python",
        fn_key="band_fn",
        external_key="band_transform",
        default_fn="band",
        config_dir=config_dir,
        hook_label=hook_label,
    )
    if fn is not None:
        low, high = fn(*[np.asarray(a) for a in ys])
        return np.asarray(low), np.asarray(high)

    raise ConfigError(
        "A combine series' 'band' must be 'std' (spread across the inputs) "
        "or come with a 'band_python'/'band_transform' hook returning "
        "(lower, upper)."
    )


def _align_arrays(arrs, mode="min"):
    lens = [len(a) for a in arrs]
    if len(set(lens)) == 1:
        return arrs
    if mode == "error":
        raise ValueError(f"Array length mismatch: {lens}")
    m = min(lens)
    return [a[:m] for a in arrs]



_TEXT_BOX_POSITIONS = {
    "top_left": (0.02, 0.98, "left", "top"),
    "top_center": (0.50, 0.98, "center", "top"),
    "top_right": (0.98, 0.98, "right", "top"),
    "middle_left": (0.02, 0.50, "left", "center"),
    "center": (0.50, 0.50, "center", "center"),
    "middle_right": (0.98, 0.50, "right", "center"),
    "bottom_left": (0.02, 0.02, "left", "bottom"),
    "bottom_center": (0.50, 0.02, "center", "bottom"),
    "bottom_right": (0.98, 0.02, "right", "bottom"),
}


def _add_text_boxes(ax, cfg):
    """Add YAML-configured text boxes in normalized axes coordinates."""
    for spec in cfg.get("text_boxes", []):
        position = spec.get("position", "center")

        if isinstance(position, str):
            if position not in _TEXT_BOX_POSITIONS:
                allowed = ", ".join(_TEXT_BOX_POSITIONS)
                raise ValueError(
                    f"Unknown text box position '{position}'. "
                    f"Use one of: {allowed}, or [x, y]."
                )
            x, y, default_ha, default_va = _TEXT_BOX_POSITIONS[position]
        elif isinstance(position, (list, tuple)) and len(position) == 2:
            x, y = float(position[0]), float(position[1])
            default_ha, default_va = "center", "center"
        else:
            raise ValueError(
                "text box 'position' must be a named position or [x, y]."
            )

        offset = spec.get("offset", [0.0, 0.0])
        if not isinstance(offset, (list, tuple)) or len(offset) != 2:
            raise ValueError("text box 'offset' must be [dx, dy].")
        x += float(offset[0])
        y += float(offset[1])

        text_align = spec.get("text_align", "left")
        if text_align == "middle":
            text_align = "center"
        if text_align not in {"left", "center", "right"}:
            raise ValueError(
                "text box 'text_align' must be left, center/middle, or right."
            )

        box_cfg = spec.get("box", {})
        bbox = None
        if box_cfg is not False:
            bbox = {
                "boxstyle": (
                    f"{box_cfg.get('style', 'round')},"
                    f"pad={box_cfg.get('padding', 0.5)}"
                ),
                "facecolor": box_cfg.get("facecolor", "white"),
                "edgecolor": box_cfg.get("edgecolor", "black"),
                "linewidth": box_cfg.get("linewidth", 1.0),
                "linestyle": box_cfg.get("linestyle", "-"),
                "alpha": box_cfg.get("alpha", 1.0),
            }

        ax.text(
            x, y,
            spec.get("text", ""),
            transform=ax.transAxes,
            horizontalalignment=spec.get("horizontal_align", default_ha),
            verticalalignment=spec.get("vertical_align", default_va),
            multialignment=text_align,
            fontsize=spec.get("font_size", cfg.get("font_size_axes", None)),
            color=spec.get("text_color", None),
            fontweight=spec.get("font_weight", None),
            fontstyle=spec.get("font_style", None),
            rotation=spec.get("rotation", 0),
            zorder=spec.get("zorder", 10),
            clip_on=spec.get("clip_on", False),
            bbox=bbox,
        )

# ============================================================
# Plot rendering
# ============================================================

def _configure_text_rendering(cfg):
    """
    Apply the text-related Matplotlib settings used by one plot config.

    This mutates the global rcParams, so every entry point renders inside
    _text_rendering_scope() to guarantee the process-wide state is restored.
    """
    plt.rcParams["text.usetex"] = bool(cfg.get("use_tex", False))
    if "font_size_axes" in cfg:
        plt.rcParams["font.size"] = cfg["font_size_axes"]
    if "latex_preamble" in cfg:
        preamble = cfg["latex_preamble"]
        if isinstance(preamble, list):
            preamble = "\n".join(preamble)
        plt.rcParams["text.latex.preamble"] = preamble


def _text_rendering_scope():
    """Restore the global rcParams once a figure has been rendered."""
    return plt.rc_context()


def _render_plot_on_axes(
    cfg,
    fig,
    ax,
    *,
    show_title=True,
    show_legend=True,
    show_x_label=True,
    show_y_label=True,
    allow_x_log=True,
    allow_y_log=True,
    manage_figure_layout=False,
    config_dir=None,
):
    """
    Render one normal plot config into an existing Matplotlib axes.

    The switches only suppress local features. When they are true, the local
    YAML remains authoritative.
    """
    _configure_text_rendering(cfg)

    series = cfg["series"]
    n = len(series)
    bg = cfg["background_color"]

    style_cycle = _get_styles(n, cfg["line_styles"])
    color_cycle = _get_colors(n, cfg["colors"], background_color=bg)
    marker_cycle = _get_markers(n, cfg["markers"])
    end_list_global = cfg["end_list_global"]

    ax.set_facecolor(bg)
    all_y = []
    legend_colors = {}

    # --------------------------------------------------------
    # Process each series
    # --------------------------------------------------------

    for i, spec in enumerate(series):
        stype = spec.get("type", "single")
        label = spec.get("label", f"series_{i}")
        local_end = spec.get("end_list", spec.get("end", None))
        end = local_end
        if end_list_global is not None:
            if local_end is None:
                end = end_list_global
            else:
                end = min(end_list_global, local_end)

        diag_label = f"series[{i}]"
        x_column = spec.get("x_column", cfg["x_column"])
        x = None
        low = high = None

        if stype == "single":
            csv_path = spec["csv"]
            column = spec["column"]
            df = _read_csv(csv_path, end, config_dir)

            fn = _resolve_hook(
                spec,
                inline_key="df_python",
                fn_key="df_fn",
                external_key="df_transform",
                default_fn="transform_df",
                config_dir=config_dir,
                hook_label=diag_label,
            )
            if fn is not None:
                df = fn(df)

            y = _column(df, column, csv_path)

            fn = _resolve_hook(
                spec,
                inline_key="y_python",
                fn_key="y_fn",
                external_key="y_transform",
                default_fn="transform_y",
                config_dir=config_dir,
                hook_label=diag_label,
            )
            if fn is not None:
                y = np.asarray(fn(y, df))

            if x_column is not None:
                x = _column(df, x_column, csv_path)

            low, high = _resolve_band(spec, df, csv_path, y, config_dir, diag_label)

        elif stype == "combine":
            ys = []
            names = []
            frames = []

            for inp in spec["inputs"]:
                inp_path = inp["csv"]
                df = _read_csv(inp_path, end, config_dir)
                frames.append((df, inp_path))
                ys.append(_column(df, inp["column"], inp_path))
                names.append(inp.get("name"))

            align = spec.get("align", "min")
            ys = _align_arrays(ys, align)
            fn = _resolve_hook(
                spec,
                inline_key="python",
                fn_key="fn",
                external_key="combine_transform",
                default_fn="combine",
                config_dir=config_dir,
                hook_label=diag_label,
            )

            if all(names):
                y = fn(**dict(zip(names, ys)))
            else:
                y = fn(*ys)

            y = np.asarray(y)

            if x_column is not None:
                first_df, first_path = frames[0]
                x = _column(first_df, x_column, first_path)

            low, high = _resolve_combine_band(
                spec, ys, y, align, config_dir, diag_label
            )

        else:
            raise ConfigError(f"Unknown series type: {stype}")

        if x is None:
            x = np.arange(1, len(y) + 1)
        elif len(x) != len(y):
            x, y = _align_arrays([np.asarray(x), np.asarray(y)], "min")

        all_y.append(y)

        # A series-level style is a single value. Accept a one-element list
        # so composite series_overrides can reuse the plural figure-level key.
        local_style = spec.get(
            "line_styles", spec.get("line_style", style_cycle[i])
        )
        if _is_dash_pattern(local_style):
            local_style = (local_style[0], tuple(local_style[1]))
        elif isinstance(local_style, (list, tuple)):
            local_style = local_style[i % len(local_style)]
        local_color = spec.get("color", color_cycle[i])
        local_lw = spec.get("line_width", cfg["line_width"])
        local_alpha = spec.get("alpha", cfg["alpha"])
        local_zorder = spec.get("zorder", None)

        local_marker = spec.get("marker", spec.get("markers", marker_cycle[i]))
        if isinstance(local_marker, (list, tuple)):
            local_marker = local_marker[i % len(local_marker)]

        plot_kwargs = {
            "color": local_color,
            "linestyle": local_style,
            "linewidth": local_lw,
            "alpha": local_alpha,
            "label": label,
        }
        if local_marker:
            plot_kwargs["marker"] = local_marker
            plot_kwargs["markersize"] = spec.get(
                "marker_size", cfg["marker_size"]
            )
            marker_every = spec.get("marker_every", cfg["marker_every"])
            if marker_every is not None:
                plot_kwargs["markevery"] = marker_every
        if local_zorder is not None:
            plot_kwargs["zorder"] = local_zorder

        # Draw the band first so the line stays readable on top of it.
        if low is not None:
            band_x, band_low, band_high = _align_arrays(
                [np.asarray(x), np.asarray(low), np.asarray(high)], "min"
            )
            fill_kwargs = {
                "color": spec.get("band_color", local_color),
                "alpha": spec.get("band_alpha", 0.20),
                "linewidth": 0,
            }
            if local_zorder is not None:
                fill_kwargs["zorder"] = local_zorder - 0.1
            ax.fill_between(band_x, band_low, band_high, **fill_kwargs)
            all_y.extend([np.asarray(band_low), np.asarray(band_high)])

        ax.plot(x, y, **plot_kwargs)

        if "legend_color" in spec and label not in legend_colors:
            legend_colors[label] = spec["legend_color"]

    # --------------------------------------------------------
    # Axes & styling
    # --------------------------------------------------------

    axes_font_size = cfg["font_size_axes"]
    ax.set_title(
        cfg["title"] if show_title else "",
        fontsize=cfg["font_size_title"],
    )
    ax.set_xlabel(
        cfg["x_label"] if show_x_label else "",
        fontsize=axes_font_size,
    )
    ax.set_ylabel(
        cfg["y_label"] if show_y_label else "",
        fontsize=axes_font_size,
    )
    ax.tick_params(axis="both", which="both", labelsize=axes_font_size)

    if allow_x_log and cfg["x_log"]:
        ax.set_xscale("log")
    else:
        ax.set_xscale("linear")

    if allow_y_log and cfg["y_log"]:
        ax.set_yscale("log")
    else:
        ax.set_yscale("linear")

    _apply_axis_limits(ax, "y", cfg["y_axis_set"], all_y)
    _apply_axis_limits(ax, "x", cfg["x_axis_set"], None)

    if cfg["use_grid"]:
        ax.grid(
            True,
            which="major",
            linestyle=cfg["grid_style"],
            alpha=cfg["grid_alpha"],
        )
        if cfg["minor_grid"]:
            ax.minorticks_on()
            divisions = cfg["minor_grid_divisions"]
            ax.xaxis.set_minor_locator(AutoMinorLocator(divisions))
            ax.yaxis.set_minor_locator(AutoMinorLocator(divisions))
            ax.grid(
                True,
                which="minor",
                linestyle=cfg["minor_grid_style"],
                alpha=cfg["minor_grid_alpha"],
            )

    # The legend and the layout are independent of the grid.
    outside = cfg["legend_outside"]
    draw_legend = show_legend and cfg["show_legend"]

    if draw_legend:
        legend_kwargs = {
            "fontsize": cfg["font_size_legends"],
            "loc": cfg["legend_loc"]
            or ("center left" if outside else "best"),
            "ncol": cfg["legend_columns"],
            "frameon": cfg["legend_frame"],
        }
        if outside:
            legend_kwargs["bbox_to_anchor"] = tuple(
                cfg["legend_bbox"] or [1.02, 0.5]
            )
        elif cfg["legend_bbox"] is not None:
            legend_kwargs["bbox_to_anchor"] = tuple(cfg["legend_bbox"])

        ax.legend(**legend_kwargs)

        if outside and manage_figure_layout:
            fig.subplots_adjust(right=cfg["right_margin"])

    # tight_layout would recompute margins and discard the right_margin
    # reserved above for an outside legend.
    if manage_figure_layout and not (draw_legend and outside):
        fig.tight_layout()

    _apply_foreground_contrast(ax, bg)

    leg = ax.get_legend()
    if leg is not None:
        for text, spec in zip(leg.get_texts(), series):
            if "legend_color" in spec:
                text.set_color(spec["legend_color"])

    _add_text_boxes(ax, cfg)
    return legend_colors


def _save_figure(fig, out, dpi=300, formats=("png", "pdf")):
    out_dir = os.path.dirname(out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    written = []
    for fmt in formats:
        path = f"{out}.{fmt}"
        fig.savefig(
            path,
            dpi=dpi,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
        )
        written.append(path)
    plt.close(fig)

    print("\033[1;33mSaved " + " ".join(written) + "\033[0m")


def plot_from_config(cfg, where="config", config_dir=None):
    """
    Render one normal YAML plot config exactly as a standalone figure.

    config_dir anchors any relative 'x_transform' file path in the config;
    pass the directory containing the YAML file at 'where' when known.
    """
    cfg = normalise_plot_config(cfg, where)
    if "output_basename" not in cfg:
        raise ConfigError(f"{where} requires 'output_basename'.")

    with _text_rendering_scope():
        _configure_text_rendering(cfg)

        bg = cfg["background_color"]
        fig, ax = plt.subplots(figsize=tuple(cfg["figsize"]))
        fig.patch.set_facecolor(bg)

        try:
            _render_plot_on_axes(
                cfg,
                fig,
                ax,
                manage_figure_layout=True,
                config_dir=config_dir,
            )
            _save_figure(
                fig,
                cfg["output_basename"],
                dpi=cfg["dpi"],
                formats=cfg["formats"],
            )
        except Exception:
            plt.close(fig)
            raise


# ============================================================
# Composite figures
# ============================================================

def _is_composite_config(cfg):
    kind = cfg.get("kind", cfg.get("type", None))
    return kind in {"composite", "multi_figure", "multi-figure"} or "figures" in cfg


def _normalise_figure_entries(cfg):
    raw_entries = cfg.get("figures")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("A composite config requires a non-empty 'figures' list.")

    entries = []
    for index, raw in enumerate(raw_entries):
        if isinstance(raw, str):
            entry = {"config": raw}
        elif isinstance(raw, dict):
            entry = dict(raw)
        else:
            raise ValueError(
                f"figures[{index}] must be a YAML path or a mapping."
            )

        if "config" not in entry:
            raise ValueError(f"figures[{index}] is missing 'config'.")
        entries.append(entry)

    return entries


def _parse_panel_position(raw, rows, columns, index):
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        row, column = raw
    elif isinstance(raw, dict):
        row = raw.get("row")
        column = raw.get("column", raw.get("col"))
    else:
        raise ValueError(
            f"figures[{index}].position must be [row, column] or "
            "{row: ..., column: ...}."
        )

    if not isinstance(row, int) or not isinstance(column, int):
        raise ValueError(
            f"figures[{index}].position row and column must be integers."
        )
    if not 1 <= row <= rows or not 1 <= column <= columns:
        raise ValueError(
            f"figures[{index}].position [{row}, {column}] is outside the "
            f"{rows} x {columns} layout. Positions start at 1."
        )

    return row - 1, column - 1


def _assign_panel_positions(entries, rows, columns):
    capacity = rows * columns
    if len(entries) > capacity:
        raise ValueError(
            f"The layout has {capacity} positions but {len(entries)} figures "
            "were provided."
        )

    assigned = {}
    occupied = {}

    # Reserve all explicitly requested locations first. This prevents an
    # earlier automatic entry from taking a later entry's requested position.
    for index, entry in enumerate(entries):
        if "position" in entry and "location" in entry:
            raise ValueError(
                f"figures[{index}] defines both 'position' and 'location'; "
                "use only one."
            )

        raw_position = entry.get("position", entry.get("location"))
        if raw_position is None:
            continue

        position = _parse_panel_position(
            raw_position, rows, columns, index
        )
        if position in occupied:
            other = occupied[position]
            row, column = position[0] + 1, position[1] + 1
            raise ValueError(
                f"figures[{index}] and figures[{other}] both request "
                f"position [{row}, {column}]."
            )

        occupied[position] = index
        assigned[index] = position

    available = [
        (row, column)
        for row in range(rows)
        for column in range(columns)
        if (row, column) not in occupied
    ]

    for index in range(len(entries)):
        if index not in assigned:
            assigned[index] = available.pop(0)

    return assigned


def _resolve_child_config_path(raw_path, composite_path):
    path = Path(os.path.expandvars(str(raw_path))).expanduser()
    if path.is_absolute():
        candidates = [path]
    else:
        candidates = []
        if composite_path is not None:
            candidates.append(Path(composite_path).resolve().parent / path)
        candidates.append(Path.cwd() / path)

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    attempted = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(
        f"Referenced plot config not found: {raw_path}. Tried: {attempted}"
    )


def _apply_series_overrides(child_cfg, overrides, path):
    """Apply composite-only values to every series without changing the YAML."""
    if not overrides:
        return child_cfg

    series = child_cfg.get("series")
    if not isinstance(series, list):
        raise ValueError(f"Referenced config has no valid 'series' list: {path}")

    overridden_cfg = dict(child_cfg)
    overridden_series = []
    for index, spec in enumerate(series):
        if not isinstance(spec, dict):
            raise ValueError(
                f"Referenced config series[{index}] is not a mapping: {path}"
            )
        overridden_spec = dict(spec)
        overridden_spec.update(overrides)
        overridden_series.append(overridden_spec)

    overridden_cfg["series"] = overridden_series
    return overridden_cfg


def _load_child_configs(entries, composite_path, series_overrides):
    loaded = []
    for index, entry in enumerate(entries):
        path = _resolve_child_config_path(entry["config"], composite_path)
        with open(path) as f:
            child_cfg = yaml.safe_load(f)

        if not isinstance(child_cfg, dict):
            raise ValueError(f"Referenced config is empty or invalid: {path}")
        if _is_composite_config(child_cfg):
            raise ValueError(
                f"Nested composite configs are not supported: {path}"
            )

        child_cfg = _apply_series_overrides(
            child_cfg,
            series_overrides,
            path,
        )
        child_cfg = normalise_plot_config(child_cfg, str(path))
        loaded.append((entry, path, child_cfg))
    return loaded


def _draw_panel_labels(fig, panels, composite_cfg):
    """
    Draw the (a)/(b)/(c) captions underneath each panel.

    The position is measured from each panel's rendered bounding box, which
    already contains the tick labels and the x label, so a caption never lands
    on top of them regardless of the figure size. Call this after the layout
    has been finalised. 'panel_label_y' still overrides with the historical
    axes-relative offset.
    """
    labelled = [item for item in panels if item[1] is not None]
    if not labelled:
        return

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    to_figure = fig.transFigure.inverted()

    for ax, label, entry, child_cfg in labelled:
        axes_box = ax.get_position()
        pad = entry.get(
            "label_pad", composite_cfg.get("panel_label_pad", 0.015)
        )

        explicit_y = entry.get(
            "label_y", composite_cfg.get("panel_label_y", None)
        )
        if explicit_y is not None:
            y = axes_box.y0 + explicit_y * axes_box.height
        else:
            tight = ax.get_tightbbox(renderer).transformed(to_figure)
            y = tight.y0 - pad

        bg = child_cfg.get("background_color", "white")
        fg = "white" if _is_dark(bg) else "black"

        fig.text(
            axes_box.x0 + axes_box.width / 2.0,
            y,
            str(label),
            horizontalalignment="center",
            verticalalignment="top",
            fontsize=entry.get(
                "label_font_size",
                composite_cfg.get(
                    "font_size_panel_labels", child_cfg["font_size_axes"]
                ),
            ),
            color=entry.get(
                "label_color", composite_cfg.get("panel_label_color", fg)
            ),
            fontweight=entry.get(
                "label_font_weight",
                composite_cfg.get("panel_label_font_weight", None),
            ),
        )


def _lift_label_clear_of_legend(fig, label_artist, legend, explicit=False):
    """
    Move the figure-level x label above a bottom legend when the two collide.

    A global legend placed under the panels lands on the same strip as the
    global x label. Rather than asking every config to hand-tune
    'global_x_label_y', measure both once the layout is final and lift the
    label only when they actually overlap. An explicit y is left alone.
    """
    if label_artist is None or legend is None or explicit:
        return

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    to_figure = fig.transFigure.inverted()

    legend_box = legend.get_window_extent(renderer).transformed(to_figure)
    label_box = label_artist.get_window_extent(renderer).transformed(to_figure)

    overlaps = label_box.y0 < legend_box.y1 and label_box.y1 > legend_box.y0
    if not overlaps:
        return

    label_artist.set_y(legend_box.y1 + 0.015)
    label_artist.set_verticalalignment("bottom")


def _collect_unique_legend_entries(axes_in_order):
    unique = {}
    for ax in axes_in_order:
        handles, labels = ax.get_legend_handles_labels()
        for handle, label in zip(handles, labels):
            if not label or label.startswith("_") or label in unique:
                continue
            unique[label] = handle
    return list(unique.values()), list(unique.keys())


def _local_feature_enabled(cfg, name):
    """
    Return whether a local feature should be preserved.

    The concise plural key is preferred (for example, legends: false). The
    local_ prefix is accepted as an alias for readability and compatibility
    with configs that use local_legends: false.
    """
    alias = f"local_{name}"
    if name in cfg and alias in cfg and cfg[name] != cfg[alias]:
        raise ValueError(
            f"Composite config has conflicting '{name}' and '{alias}' values."
        )
    value = cfg.get(name, cfg.get(alias, True))
    return value is not False


def _add_global_legend(fig, cfg, axes_in_order, legend_colors, bg):
    handles, labels = _collect_unique_legend_entries(axes_in_order)
    if not handles:
        print("Warning: global_legend is enabled, but no series labels were found.")
        return None

    loc = cfg.get("legend_loc", "upper center")
    if loc == "best":
        print(
            "Warning: 'best' is not available for a figure-level legend; "
            "using 'upper right'."
        )
        loc = "upper right"

    kwargs = {
        "fontsize": cfg.get("font_size_legends", 12),
        "loc": loc,
        "ncol": cfg.get("legend_columns", 1),
    }

    if "legend_bbox" in cfg:
        kwargs["bbox_to_anchor"] = tuple(cfg["legend_bbox"])
    elif cfg.get("legend_outside", False):
        kwargs["bbox_to_anchor"] = (1.02, 0.5)

    legend = fig.legend(handles, labels, **kwargs)

    fg = cfg.get(
        "global_foreground_color", "white" if _is_dark(bg) else "black"
    )
    frame = legend.get_frame()
    frame.set_facecolor(cfg.get("legend_facecolor", bg))
    frame.set_edgecolor(cfg.get("legend_edgecolor", fg))
    for text, label in zip(legend.get_texts(), labels):
        text.set_color(legend_colors.get(label, fg))

    return legend


def plot_composite_from_config(cfg, composite_path=None):
    """Render a multi-panel figure whose panels are normal plot YAML files."""
    with _text_rendering_scope():
        return _render_composite(cfg, composite_path)


def _render_composite(cfg, composite_path=None):
    normalise_composite_config(cfg)
    rows = cfg.get("rows")
    columns = cfg.get("columns")
    if not isinstance(rows, int) or rows < 1:
        raise ValueError("Composite 'rows' must be a positive integer.")
    if not isinstance(columns, int) or columns < 1:
        raise ValueError("Composite 'columns' must be a positive integer.")

    entries = _normalise_figure_entries(cfg)
    positions = _assign_panel_positions(entries, rows, columns)

    series_overrides = cfg.get("series_overrides", {})
    if series_overrides is None:
        series_overrides = {}
    if not isinstance(series_overrides, dict):
        raise ValueError("Composite 'series_overrides' must be a mapping.")

    loaded = _load_child_configs(
        entries,
        composite_path,
        series_overrides,
    )

    # Composite text settings apply only to figure-level title/labels. Local
    # panel text continues to use each referenced YAML's settings.
    first_child = loaded[0][2]
    global_text_cfg = {
        "use_tex": cfg.get("use_tex", first_child.get("use_tex", False)),
        "font_size_axes": cfg.get(
            "font_size_global_axes", first_child["font_size_axes"]
        ),
    }
    if "latex_preamble" in cfg:
        global_text_cfg["latex_preamble"] = cfg["latex_preamble"]
    elif "latex_preamble" in first_child:
        global_text_cfg["latex_preamble"] = first_child["latex_preamble"]
    _configure_text_rendering(global_text_cfg)

    figsize = cfg.get("figsize", [6 * columns, 4 * rows])
    if not isinstance(figsize, (list, tuple)) or len(figsize) != 2:
        raise ValueError("Composite 'figsize' must be [width, height].")

    bg = cfg.get("background_color", "white")
    fig, axes = plt.subplots(
        rows,
        columns,
        figsize=tuple(figsize),
        squeeze=False,
    )
    fig.patch.set_facecolor(bg)

    show_titles = _local_feature_enabled(cfg, "titles")
    show_legends = _local_feature_enabled(cfg, "legends")
    show_x_labels = _local_feature_enabled(cfg, "x_labels")
    show_y_labels = _local_feature_enabled(cfg, "y_labels")
    allow_x_logs = _local_feature_enabled(cfg, "x_logs")
    allow_y_logs = _local_feature_enabled(cfg, "y_logs")

    used_positions = set()
    axes_in_figure_order = []
    legend_colors = {}
    panels = []

    try:
        for index, (entry, path, child_cfg) in enumerate(loaded):
            row, column = positions[index]
            ax = axes[row][column]
            used_positions.add((row, column))
            axes_in_figure_order.append(ax)

            panel_legend_colors = _render_plot_on_axes(
                child_cfg,
                fig,
                ax,
                show_title=show_titles,
                show_legend=show_legends,
                show_x_label=show_x_labels,
                show_y_label=show_y_labels,
                allow_x_log=allow_x_logs,
                allow_y_log=allow_y_logs,
                manage_figure_layout=False,
                config_dir=str(path.parent),
            )
            for label, color in panel_legend_colors.items():
                legend_colors.setdefault(label, color)

            panels.append((ax, entry.get("label"), entry, child_cfg))

        for row in range(rows):
            for column in range(columns):
                if (row, column) not in used_positions:
                    axes[row][column].axis("off")

        _configure_text_rendering(global_text_cfg)
        fg = cfg.get(
            "global_foreground_color", "white" if _is_dark(bg) else "black"
        )

        global_title = cfg.get("global_title")
        if global_title not in (None, ""):
            fig.suptitle(
                global_title,
                fontsize=cfg.get(
                    "font_size_global_title", first_child["font_size_title"]
                ),
                color=cfg.get("global_title_color", fg),
                y=cfg.get("global_title_y", 0.98),
            )

        global_x_label = cfg.get("global_x_label")
        supxlabel_artist = None
        if global_x_label not in (None, ""):
            supxlabel_artist = fig.supxlabel(
                global_x_label,
                fontsize=cfg.get(
                    "font_size_global_axes", first_child["font_size_axes"]
                ),
                color=cfg.get("global_x_label_color", fg),
                x=cfg.get("global_x_label_x", 0.5),
                y=cfg.get("global_x_label_y", 0.01),
            )

        global_y_label = cfg.get("global_y_label")
        if global_y_label not in (None, ""):
            fig.supylabel(
                global_y_label,
                fontsize=cfg.get(
                    "font_size_global_axes", first_child["font_size_axes"]
                ),
                color=cfg.get("global_y_label_color", fg),
                x=cfg.get("global_y_label_x", 0.01),
                y=cfg.get("global_y_label_y", 0.5),
            )

        global_legend = None
        if cfg.get("global_legend", False):
            global_legend = _add_global_legend(
                fig,
                cfg,
                axes_in_figure_order,
                legend_colors,
                bg,
            )

        if cfg.get("tight_layout", True):
            default_left = 0.08 if global_y_label not in (None, "") else 0.03
            default_bottom = 0.10 if global_x_label not in (None, "") else 0.04
            default_top = 0.91 if global_title not in (None, "") else 0.97
            fig.tight_layout(
                rect=(
                    cfg.get("left_margin", default_left),
                    cfg.get("bottom_margin", default_bottom),
                    cfg.get("right_margin", 0.97),
                    cfg.get("top_margin", default_top),
                ),
                pad=cfg.get("layout_padding", 1.08),
                w_pad=cfg.get("horizontal_padding", None),
                h_pad=cfg.get("vertical_padding", None),
            )
        else:
            fig.subplots_adjust(
                left=cfg.get("left_margin", None),
                bottom=cfg.get("bottom_margin", None),
                right=cfg.get("right_margin", None),
                top=cfg.get("top_margin", None),
                wspace=cfg.get("horizontal_spacing", None),
                hspace=cfg.get("vertical_spacing", None),
            )

        # The layout is final, so panel captions can now be measured against
        # each panel's real bounding box.
        _draw_panel_labels(fig, panels, cfg)
        _lift_label_clear_of_legend(
            fig,
            supxlabel_artist,
            global_legend,
            explicit="global_x_label_y" in cfg,
        )

        _save_figure(
            fig,
            cfg["output_basename"],
            dpi=cfg.get("dpi", 300),
            formats=[
                f.lower() for f in _as_cycle(cfg.get("formats", ["png", "pdf"]))
            ],
        )
    except Exception:
        plt.close(fig)
        raise


# ============================================================
# Entry point
# ============================================================

#: (inline key, inline-fn key, external key, default function name) for
#: each transform hook, used to validate --check without rendering.
_TRANSFORM_HOOKS = [
    ("df_python", "df_fn", "df_transform", "transform_df"),
    ("y_python", "y_fn", "y_transform", "transform_y"),
    ("python", "fn", "combine_transform", "combine"),
    ("band_python", "band_fn", "band_transform", "band"),
]


def check_transform_hooks(cfg, config_dir):
    """
    Load every external transform reference in a config without calling it.

    Lets --check catch a bad file path or missing function name before a
    render is attempted.
    """
    for index, spec in enumerate(cfg.get("series", [])):
        if not isinstance(spec, dict):
            continue
        label = f"series[{index}]"
        for inline_key, fn_key, external_key, default_fn in _TRANSFORM_HOOKS:
            if external_key in spec:
                _resolve_hook(
                    spec,
                    inline_key=inline_key,
                    fn_key=fn_key,
                    external_key=external_key,
                    default_fn=default_fn,
                    config_dir=config_dir,
                    hook_label=label,
                )


def load_config(path):
    """Read one YAML config from disk."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path) as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ConfigError(f"Config is empty or invalid: {path}")
    return cfg


def _apply_cli_overrides(cfg, args):
    """Let command line flags win over the values written in the YAML."""
    if args.output is not None:
        cfg["output_basename"] = args.output
    if args.dpi is not None:
        cfg["dpi"] = args.dpi
    if args.format:
        cfg["formats"] = list(args.format)
    return cfg


def build_parser():
    parser = argparse.ArgumentParser(
        prog="figspec",
        description="Render a figure from a YAML plot or composite config.",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to a plot config or a composite config.",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Override 'output_basename' (no file extension).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="Override the raster output resolution.",
    )
    parser.add_argument(
        "--format",
        action="append",
        default=None,
        metavar="EXT",
        help=(
            "Override the output formats. Repeat for several, "
            f"e.g. --format pdf --format svg. Supported: "
            f"{', '.join(sorted(SUPPORTED_FORMATS))}."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the config and report problems without rendering.",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        cfg = load_config(args.config)
        composite = _is_composite_config(cfg)
        cfg = _apply_cli_overrides(cfg, args)

        if args.check:
            if composite:
                normalise_composite_config(cfg)
                for _, path, child_cfg in _load_child_configs(
                    _normalise_figure_entries(cfg),
                    args.config,
                    cfg.get("series_overrides") or {},
                ):
                    check_transform_hooks(child_cfg, str(path.parent))
                    print(f"  panel OK: {path}")
                print(f"{args.config}: composite config is valid.")
            else:
                cfg = normalise_plot_config(cfg, args.config)
                config_dir = os.path.dirname(os.path.abspath(args.config))
                check_transform_hooks(cfg, config_dir)
                print(f"{args.config}: config is valid.")
            return 0

        if composite:
            plot_composite_from_config(cfg, composite_path=args.config)
        else:
            config_dir = os.path.dirname(os.path.abspath(args.config))
            plot_from_config(cfg, where=args.config, config_dir=config_dir)
    except (ConfigError, FileNotFoundError, KeyError) as exc:
        print(f"\033[1;31mError:\033[0m {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
