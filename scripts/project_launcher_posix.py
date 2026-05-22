#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
POSIX compatibility entrypoint for vibe-coding-guidelines.

This keeps the split-platform workflow from the source skill available while
delegating to the local unified project_launcher.py implementation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import project_launcher as shared


VERSION = "2026-03-07.compat"
DEFAULT_VENV_DIR = shared.DEFAULT_VENV_DIR


def main() -> int:
    ap = argparse.ArgumentParser(
        description="POSIX compatibility launcher wrapper for project_launcher.py"
    )
    ap.add_argument("--root", type=str, default=".", help="Project root")
    ap.add_argument("--venv", type=str, default=DEFAULT_VENV_DIR, help="Venv directory")
    ap.add_argument(
        "--package",
        action="store_true",
        help="Generate launch scripts and package a ZIP via the shared launcher",
    )
    ap.add_argument(
        "--package-out",
        type=str,
        default="",
        help="Optional ZIP output path when used with --package",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    print(f"[LAUNCHER] version={VERSION} file={Path(__file__).resolve()}")

    if args.package:
        try:
            out_bat, out_sh, out_cmd = shared.generate_launch_scripts(root, args.venv)
            out_zip = (
                Path(args.package_out).expanduser().resolve()
                if args.package_out
                else (root / "release" / f"{root.name}.zip").resolve()
            )
            if out_zip.exists():
                from datetime import datetime

                out_zip = out_zip.with_name(
                    f"{out_zip.stem}-{datetime.now().strftime('%Y%m%d-%H%M%S')}{out_zip.suffix}"
                )
            out_zip = shared.package_project_zip(root, out_zip)
        except Exception as exc:
            print(f"[ERROR] {exc}")
            return 1

        print("OK: launch scripts and ZIP package generated.")
        print(f"- run_app.bat: {out_bat}")
        print(f"- run_app.sh: {out_sh}")
        print(f"- run_app.command: {out_cmd}")
        print(f"- zip: {out_zip}")
        return 0

    code, msg = shared.full_auto(root, args.venv)
    print(msg)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
