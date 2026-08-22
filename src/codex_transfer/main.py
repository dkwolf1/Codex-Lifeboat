from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import backup, restore
from .gui import run_gui
from .selftest import run_self_test
from .validate import validate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Codex Lifeboat")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--work")
    parser.add_argument("--validate")
    parser.add_argument("--verify-restored")
    parser.add_argument("--target-profile")
    return parser.parse_args()


def main() -> int:
    # PyInstaller one-file apps can be launched from transient Windows locations
    # (for example, directly from a ZIP). Preserve a stable copy while the launch
    # path still exists so a later backup can include the restore application.
    backup.stage_runtime_executable()
    args = parse_args()
    if args.self_test:
        result = run_self_test(Path(args.work) if args.work else None)
        if sys.stdout is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("passed") else 1
    if args.validate:
        result = validate(Path(args.validate), False)
        if sys.stdout is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("valid") else 1
    if args.verify_restored:
        target = Path(args.target_profile) if args.target_profile else Path.home()
        result = restore.verify_restored(Path(args.verify_restored), target)
        if sys.stdout is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("valid") else 1
    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
