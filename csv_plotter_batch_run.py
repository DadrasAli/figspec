#!/usr/bin/env python3
"""
Run csv_plotter.py for all YAML configs in a folder, with optional YAML overrides.

Basic example:
python csv_plotter_batch_run.py \
  --config-dir csv_plots/csv_configs/adaptive_lr/mnist \
  --plotter csv_plotter.py

Generic overrides:
python csv_plotter_batch_run.py \
  --config-dir csv_plots/csv_configs/adaptive_lr/mnist \
  --plotter csv_plotter.py \
  --set line_width 5 \
  --set figsize "[9, 5]" \
  --set font_size_title 20 \
  --set font_size_axes 18 \
  --set font_size_legends 14 \
  --set legend_outside false \
  --set legend_columns 1

Equivalent KEY=VALUE style:
python csv_plotter_batch_run.py \
  --config-dir csv_plots/csv_configs/adaptive_lr/mnist/eta_over_S \
  --plotter csv_plotter.py \
  --set line_width=7 \
  --set "figsize=[11, 7]" \
  --set font_size_title=30 \
  --set font_size_axes=28 \
  --set font_size_legends=26 \
  --set legend_outside=true \
  --set legend_columns=3 \
  --set legend_loc="lower center"\
  --set "legend_bbox=[0.5, 1.02]"\
  --set right_margin=1

Notes:
- Values are parsed as YAML:
    false -> bool
    1     -> int
    5.0   -> float
    [9,5] -> list
- For a simple key like line_width, --set updates the top-level YAML key and
  also updates matching keys inside every series entry when they exist there.
"""



import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


def find_configs(config_dir: Path, recursive: bool) -> list[Path]:
    patterns = ["*.yaml", "*.yml"]

    configs: list[Path] = []
    for pattern in patterns:
        if recursive:
            configs.extend(config_dir.rglob(pattern))
        else:
            configs.extend(config_dir.glob(pattern))

    return sorted(p for p in configs if p.is_file())


def parse_yaml_value(raw: str) -> Any:
    """Parse command-line override values using YAML syntax."""
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"Could not parse value as YAML: {raw}") from exc


def parse_override(tokens: list[str]) -> tuple[str, Any]:
    """
    Accept both:
      --set key value
      --set key=value
    """
    if len(tokens) == 1:
        if "=" not in tokens[0]:
            raise ValueError(
                f"Invalid override '{tokens[0]}'. Use KEY=VALUE or KEY VALUE."
            )
        key, raw_value = tokens[0].split("=", 1)
    elif len(tokens) >= 2:
        key = tokens[0]
        raw_value = " ".join(tokens[1:])
    else:
        raise ValueError("Empty override.")

    key = key.strip()
    if not key:
        raise ValueError("Override key cannot be empty.")

    return key, parse_yaml_value(raw_value)


def update_matching_series_keys(cfg: dict, key: str, value: Any) -> int:
    """
    Update key in each series entry where the key already exists.
    This is useful for configs where line_width is set per CSV series.
    """
    count = 0
    series = cfg.get("series", [])

    if not isinstance(series, list):
        return count

    for spec in series:
        if isinstance(spec, dict) and key in spec:
            spec[key] = value
            count += 1

    return count


def set_all_series_key(cfg: dict, key: str, value: Any) -> int:
    """Force-set key=value in every series entry."""
    count = 0
    series = cfg.get("series", [])

    if not isinstance(series, list):
        return count

    for spec in series:
        if isinstance(spec, dict):
            spec[key] = value
            count += 1

    return count


def set_path(obj: Any, path: str, value: Any) -> int:
    """
    Set a nested YAML path.

    Supported examples:
      series.0.line_width
      series.*.line_width
      text_boxes.0.font_size

    Returns the number of assignments made.
    """
    parts = path.split(".")

    def _set(current: Any, remaining: list[str]) -> int:
        part = remaining[0]
        is_last = len(remaining) == 1

        if part == "*":
            if isinstance(current, list):
                return sum(_set(item, remaining[1:]) for item in current)
            if isinstance(current, dict):
                return sum(_set(item, remaining[1:]) for item in current.values())
            return 0

        if isinstance(current, list):
            try:
                idx = int(part)
            except ValueError:
                return 0

            if idx < 0 or idx >= len(current):
                return 0

            if is_last:
                current[idx] = value
                return 1

            return _set(current[idx], remaining[1:])

        if isinstance(current, dict):
            if is_last:
                current[part] = value
                return 1

            if part not in current:
                return 0

            return _set(current[part], remaining[1:])

        return 0

    return _set(obj, parts)


def apply_named_set(cfg: dict, key: str, value: Any) -> None:
    """
    Apply a simple --set key value override.

    Behavior:
    - If key contains "." or "*", treat it as a path override.
    - Otherwise:
        1) set cfg[key] = value
        2) also update matching keys inside series entries, if they exist
    """
    if "." in key or "*" in key:
        n = set_path(cfg, key, value)
        if n == 0:
            print(f"Warning: path override matched nothing: {key}")
        return

    cfg[key] = value
    n_series = update_matching_series_keys(cfg, key, value)

    if n_series > 0:
        print(f"Applied {key}={value!r} at top level and in {n_series} series entry/entries.")
    else:
        print(f"Applied {key}={value!r} at top level.")


def apply_overrides(cfg: dict, args: argparse.Namespace) -> dict:
    """Apply all requested YAML overrides to one loaded config."""

    # Backward-compatible convenience flags from the earlier version.
    if args.line_width is not None:
        apply_named_set(cfg, "line_width", args.line_width)

    if args.figsize is not None:
        apply_named_set(cfg, "figsize", [args.figsize[0], args.figsize[1]])

    if args.font_size_title is not None:
        apply_named_set(cfg, "font_size_title", args.font_size_title)

    if args.font_size_axes is not None:
        apply_named_set(cfg, "font_size_axes", args.font_size_axes)

    if args.font_size_legends is not None:
        apply_named_set(cfg, "font_size_legends", args.font_size_legends)

    # Generic top-level/path overrides.
    for tokens in args.set or []:
        key, value = parse_override(tokens)
        apply_named_set(cfg, key, value)

    # Generic all-series overrides.
    for tokens in args.set_series or []:
        key, value = parse_override(tokens)
        n = set_all_series_key(cfg, key, value)
        print(f"Applied series.{key}={value!r} in {n} series entry/entries.")

    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run csv_plotter.py for all YAML configs in a folder."
    )

    parser.add_argument(
        "--config-dir",
        required=True,
        help="Folder containing YAML plot configs.",
    )
    parser.add_argument(
        "--plotter",
        default="csv_plotter.py",
        help="Path to csv_plotter.py.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Also search configs inside subfolders.",
    )
    parser.add_argument(
        "--cwd",
        default=".",
        help=(
            "Working directory for running csv_plotter.py. "
            "Use your project root if CSV/output paths are relative."
        ),
    )
    parser.add_argument(
        "--keep-temp-configs",
        action="store_true",
        help="Keep the generated temporary configs for inspection.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without running them.",
    )

    # Generic override system.
    parser.add_argument(
        "--set",
        nargs="+",
        action="append",
        default=[],
        metavar=("KEY", "VALUE"),
        help=(
            "Override a YAML value. Use either '--set key value' or '--set key=value'. "
            "Simple keys update the top-level key and matching series keys. "
            "Dotted paths are supported, e.g. '--set series.*.line_width 5'."
        ),
    )
    parser.add_argument(
        "--set-series",
        nargs="+",
        action="append",
        default=[],
        metavar=("KEY", "VALUE"),
        help=(
            "Force-set a key in every entry under series:. "
            "Use either '--set-series key value' or '--set-series key=value'."
        ),
    )

    # Convenience aliases kept from the first version.
    parser.add_argument("--line-width", type=float, default=None)
    parser.add_argument("--figsize", type=float, nargs=2, metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--font-size-title", type=int, default=None)
    parser.add_argument("--font-size-axes", type=int, default=None)
    parser.add_argument("--font-size-legends", type=int, default=None)

    args = parser.parse_args()

    config_dir = Path(args.config_dir).expanduser().resolve()
    plotter = Path(args.plotter).expanduser().resolve()
    cwd = Path(args.cwd).expanduser().resolve()

    if not config_dir.is_dir():
        raise NotADirectoryError(f"Config folder not found: {config_dir}")

    if not plotter.is_file():
        raise FileNotFoundError(f"csv_plotter.py not found: {plotter}")

    configs = find_configs(config_dir, recursive=args.recursive)

    if not configs:
        print(f"No YAML configs found in: {config_dir}")
        return

    print(f"Found {len(configs)} config(s).")

    if args.keep_temp_configs:
        temp_root = cwd / ".tmp_csv_plotter_configs"
        temp_root.mkdir(parents=True, exist_ok=True)
        cleanup_temp = False
        temp_dir = None
    else:
        temp_dir = tempfile.TemporaryDirectory(prefix="csv_plotter_configs_")
        temp_root = Path(temp_dir.name)
        cleanup_temp = True

    try:
        for cfg_path in configs:
            print(f"\nConfig: {cfg_path}")

            with open(cfg_path, "r") as f:
                cfg = yaml.safe_load(f)

            if cfg is None:
                print(f"Skipping empty config: {cfg_path}")
                continue

            cfg = apply_overrides(cfg, args)

            rel_name = cfg_path.relative_to(config_dir)
            temp_cfg_path = temp_root / rel_name
            temp_cfg_path.parent.mkdir(parents=True, exist_ok=True)

            with open(temp_cfg_path, "w") as f:
                yaml.safe_dump(cfg, f, sort_keys=False)

            cmd = [
                sys.executable,
                str(plotter),
                "--config",
                str(temp_cfg_path),
            ]

            print("Running:")
            print(" ".join(cmd))

            if not args.dry_run:
                subprocess.run(cmd, cwd=str(cwd), check=True)

        if args.keep_temp_configs:
            print(f"\nTemporary configs kept in: {temp_root}")

    finally:
        if cleanup_temp and temp_dir is not None:
            temp_dir.cleanup()


if __name__ == "__main__":
    main()