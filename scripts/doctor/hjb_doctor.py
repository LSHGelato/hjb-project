#!/usr/bin/env python3
"""
HJB Doctor (preflight checks)

Purpose:
- Validate local + NAS prerequisites before running watchers or tasks.
- Fail fast with clear diagnostics and a stable exit code.

Design:
- Reads config/config.yaml if present, else config/config.example.yaml.
- Enforces scratch disk contract (C:\\Scratch\\NVMe + required subfolders).
- Verifies NAS state directories exist and are writable (write+delete test).

Exit codes:
  0 = OK
  2 = Config error (missing / parse / required keys)
  3 = Scratch error (missing root or required subfolders)
  4 = NAS path error (missing required dirs)
  5 = NAS write test failed
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml


REQUIRED_SCRATCH_SUBDIRS = [
    "_tmp",
    "_cache",
    "_staging",
    "_working",
    "_spool",
    "_logs",
    "_quarantine",
]


@dataclass(frozen=True)
class Paths:
    state_root: Path
    flags_root: Path
    logs_root: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def load_yaml(path: Path) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a YAML mapping (dict): {path}")
    return data


def find_repo_root(start: Path) -> Path:
    # Walk upwards until we find a .git folder or README.md; default to script parents.
    cur = start.resolve()
    for _ in range(8):
        if (cur / ".git").exists() or (cur / "README.md").exists():
            return cur
        cur = cur.parent
    return start.resolve().parents[2]


def get_config(repo_root: Path, config_path: Optional[str]) -> Tuple[Path, Dict[str, Any]]:
    if config_path:
        p = Path(config_path)
        if not p.is_file():
            raise FileNotFoundError(f"--config not found: {p}")
        return p, load_yaml(p)

    cfg = repo_root / "config" / "config.yaml"
    if cfg.is_file():
        return cfg, load_yaml(cfg)

    cfg_ex = repo_root / "config" / "config.example.yaml"
    if cfg_ex.is_file():
        return cfg_ex, load_yaml(cfg_ex)

    raise FileNotFoundError("Neither config/config.yaml nor config/config.example.yaml found.")


def parse_scratch_root(cfg: Dict[str, Any]) -> Path:
    # Accept either:
    #  - scratch_root: "C:\\Scratch\\NVMe"
    #  - scratch: { root: "C:\\Scratch\\NVMe" }
    v = cfg.get("scratch_root")
    if isinstance(v, str) and v.strip():
        return Path(v.strip())

    scratch = cfg.get("scratch")
    if isinstance(scratch, dict):
        v2 = scratch.get("root")
        if isinstance(v2, str) and v2.strip():
            return Path(v2.strip())

    raise KeyError("Missing scratch root (expected top-level scratch_root or scratch.root)")


def parse_paths(cfg: Dict[str, Any]) -> Paths:
    paths = cfg.get("paths")
    if not isinstance(paths, dict):
        raise KeyError("Missing paths block (expected 'paths:' mapping in config)")

    def req(key: str) -> str:
        v = paths.get(key)
        if not (isinstance(v, str) and v.strip()):
            raise KeyError(f"Missing required config key: paths.{key}")
        return v.strip()

    return Paths(
        state_root=Path(req("state_root")),
        flags_root=Path(req("flags_root")),
        logs_root=Path(req("logs_root")),
    )


def require_dir(p: Path, label: str) -> None:
    if not p.exists():
        raise FileNotFoundError(f"{label} does not exist: {p}")
    if not p.is_dir():
        raise NotADirectoryError(f"{label} is not a directory: {p}")


def check_scratch(scratch_root: Path) -> None:
    require_dir(scratch_root, "SCRATCH_ROOT")
    for sub in REQUIRED_SCRATCH_SUBDIRS:
        require_dir(scratch_root / sub, f"SCRATCH subfolder '{sub}'")


def check_nas_dirs(paths: Paths) -> None:
    # Core
    require_dir(paths.state_root, "state_root")
    require_dir(paths.flags_root, "flags_root")
    require_dir(paths.logs_root, "logs_root")

    # Flags contract
    require_dir(paths.flags_root / "pending", "flags/pending")
    require_dir(paths.flags_root / "processing", "flags/processing")
    require_dir(paths.flags_root / "completed", "flags/completed")


def write_test(paths: Paths) -> None:
    # Write+delete a tiny file in logs_root to validate permissions + SMB health.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    host = socket.gethostname()
    pid = os.getpid()

    test_file = paths.logs_root / f"doctor_write_test_{host}_{pid}_{stamp}.txt"
    payload = f"HJB doctor write test OK\nutc={utc_now_iso()}\nhost={host}\npid={pid}\n"
    try:
        test_file.write_text(payload, encoding="utf-8")
    except Exception as ex:
        raise PermissionError(f"Failed to write test file: {test_file} ({ex})") from ex

    try:
        test_file.unlink(missing_ok=True)
    except Exception as ex:
        raise PermissionError(f"Failed to delete test file: {test_file} ({ex})") from ex


def main() -> int:
    ap = argparse.ArgumentParser(description="HJB preflight checks (doctor).")
    ap.add_argument("--config", default=None, help="Optional path to config YAML.")
    ap.add_argument("--no-write-test", action="store_true", help="Skip NAS write+delete test.")
    ap.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    args = ap.parse_args()

    repo_root = find_repo_root(Path(__file__))

    summary: Dict[str, Any] = {
        "utc": utc_now_iso(),
        "hostname": socket.gethostname(),
        "repo_root": str(repo_root),
        "ok": False,
        "checks": [],
    }

    try:
        cfg_path, cfg = get_config(repo_root, args.config)
        summary["config_path"] = str(cfg_path)
        summary["checks"].append({"name": "config_load", "ok": True})

        scratch_root = parse_scratch_root(cfg)
        summary["scratch_root"] = str(scratch_root)
        summary["checks"].append({"name": "scratch_key_present", "ok": True})

        paths = parse_paths(cfg)
        summary["paths"] = {
            "state_root": str(paths.state_root),
            "flags_root": str(paths.flags_root),
            "logs_root": str(paths.logs_root),
        }
        summary["checks"].append({"name": "paths_keys_present", "ok": True})

    except Exception as ex:
        summary["error"] = f"{type(ex).__name__}: {ex}"
        if args.json:
            import json
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            eprint(f"[FAIL] Config: {summary['error']}")
        return 2

    # Scratch
    try:
        check_scratch(Path(summary["scratch_root"]))
        summary["checks"].append({"name": "scratch_contract", "ok": True})
    except Exception as ex:
        summary["error"] = f"{type(ex).__name__}: {ex}"
        if args.json:
            import json
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            eprint(f"[FAIL] Scratch: {summary['error']}")
        return 3

    # NAS dirs
    try:
        p = Paths(
            state_root=Path(summary["paths"]["state_root"]),
            flags_root=Path(summary["paths"]["flags_root"]),
            logs_root=Path(summary["paths"]["logs_root"]),
        )
        check_nas_dirs(p)
        summary["checks"].append({"name": "nas_directories", "ok": True})
    except Exception as ex:
        summary["error"] = f"{type(ex).__name__}: {ex}"
        if args.json:
            import json
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            eprint(f"[FAIL] NAS paths: {summary['error']}")
        return 4

    # NAS write test
    if not args.no_write_test:
        try:
            write_test(p)
            summary["checks"].append({"name": "nas_write_test", "ok": True})
        except Exception as ex:
            summary["error"] = f"{type(ex).__name__}: {ex}"
            if args.json:
                import json
                print(json.dumps(summary, indent=2, sort_keys=True))
            else:
                eprint(f"[FAIL] NAS write test: {summary['error']}")
            return 5

    summary["ok"] = True
    if args.json:
        import json
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print("[OK] HJB doctor checks passed")
        print(f"  config:  {summary.get('config_path')}")
        print(f"  scratch: {summary.get('scratch_root')}")
        print(f"  state:   {summary['paths']['state_root']}")
        print(f"  flags:   {summary['paths']['flags_root']}")
        print(f"  logs:    {summary['paths']['logs_root']}")
        if args.no_write_test:
            print("  write test: skipped")
        else:
            print("  write test: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
