#!/usr/bin/env python3
"""
HJB Watcher (Success v0)

Goals:
- Write a heartbeat JSON file to NAS state_root
- Claim "no-op" tasks from flags/pending via atomic rename to flags/processing
- Complete tasks by moving to flags/completed
- Fail fast if scratch root or NAS state paths are missing

Design notes:
- Intentionally minimal. No OCR. No MySQL. No MediaWiki.
- Uses config/config.yaml if present, else falls back to config.example.yaml.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping/dict: {path}")
    return data


def get_config(repo_root: Path, config_path: Optional[str]) -> Dict[str, Any]:
    if config_path:
        p = Path(config_path)
        if not p.is_file():
            raise FileNotFoundError(f"--config not found: {p}")
        return load_yaml(p)

    cfg = repo_root / "config" / "config.yaml"
    if cfg.is_file():
        return load_yaml(cfg)

    cfg_ex = repo_root / "config" / "config.example.yaml"
    if cfg_ex.is_file():
        return load_yaml(cfg_ex)

    raise FileNotFoundError("Neither config/config.yaml nor config/config.example.yaml found.")


def require_dir(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"{label} is not a directory: {path}")


def atomic_rename(src: Path, dst: Path) -> bool:
    """
    Atomic task claim on the same filesystem/SMB share.
    Returns True if rename succeeded, False if another watcher beat us to it.
    """
    try:
        src.replace(dst)  # atomic rename on same volume/share
        return True
    except FileNotFoundError:
        return False
    except PermissionError:
        return False
    except OSError:
        # Any other rename failure should be treated as a "not claimed"
        return False


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def heartbeat_path(state_root: Path, watcher_id: str) -> Path:
    # Keep OrionMX canonical heartbeat filename if watcher_id is orionmx_1, else unique file.
    if watcher_id == "orionmx_1":
        return state_root / "watcher_heartbeat.json"
    return state_root / f"watcher_heartbeat_{watcher_id}.json"


def parse_paths(cfg: Dict[str, Any]) -> Dict[str, Path]:
    """
    Accepts either:
    - cfg["paths"]["state_root"] style, OR
    - cfg["state_root"] style
    """
    paths = cfg.get("paths", {})
    if not isinstance(paths, dict):
        paths = {}

    def pick(key: str) -> Optional[str]:
        v = paths.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        v2 = cfg.get(key)
        if isinstance(v2, str) and v2.strip():
            return v2.strip()
        return None

    state_root_s = pick("state_root")
    if not state_root_s:
        raise KeyError("Missing state_root (expected cfg.paths.state_root or cfg.state_root)")

    # Derived conventional subpaths under state_root
    state_root = Path(state_root_s)
    flags_root = Path(pick("flags_root") or str(state_root / "flags"))
    logs_root = Path(pick("logs_root") or str(state_root / "logs"))

    return {
        "state_root": state_root,
        "flags_root": flags_root,
        "logs_root": logs_root,
    }


def parse_scratch_root(cfg: Dict[str, Any]) -> Path:
    """
    Accepts:
    - cfg["scratch"]["root"]
    - cfg["scratch_root"]
    """
    scratch = cfg.get("scratch", {})
    if isinstance(scratch, dict):
        v = scratch.get("root")
        if isinstance(v, str) and v.strip():
            return Path(v.strip())
    v2 = cfg.get("scratch_root")
    if isinstance(v2, str) and v2.strip():
        return Path(v2.strip())
    raise KeyError("Missing scratch root (expected cfg.scratch.root or cfg.scratch_root)")


def ensure_scratch_contract(scratch_root: Path) -> None:
    require_dir(scratch_root, "SCRATCH_ROOT")
    expected = ["_tmp", "_cache", "_staging", "_working", "_spool", "_logs", "_quarantine"]
    for sub in expected:
        p = scratch_root / sub
        require_dir(p, f"SCRATCH subfolder '{sub}'")


def run_once(
    watcher_id: str,
    state_root: Path,
    flags_root: Path,
    logs_root: Path,
    poll_seconds: int,
) -> None:
    pending = flags_root / "pending"
    processing = flags_root / "processing"
    completed = flags_root / "completed"

    # Ensure required directories exist on NAS
    for p, label in [
        (state_root, "state_root"),
        (flags_root, "flags_root"),
        (pending, "flags/pending"),
        (processing, "flags/processing"),
        (completed, "flags/completed"),
        (logs_root, "logs_root"),
    ]:
        require_dir(p, label)

    # Heartbeat
    hb = heartbeat_path(state_root, watcher_id)
    hb_payload = {
        "watcher_id": watcher_id,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "utc": utc_now_iso(),
        "mode": "success_v0",
        "poll_seconds": poll_seconds,
        "status": "running",
    }
    write_json(hb, hb_payload)

    # Claim a single no-op task if present.
    # Convention: files starting with "noop_" in flags/pending are safe Success v0 tasks.
    candidates = sorted([p for p in pending.glob("noop_*") if p.is_file()])
    for src in candidates[:1]:
        dst = processing / f"{src.name}.{watcher_id}.processing"
        if not atomic_rename(src, dst):
            continue  # another watcher got it

        # "Process" no-op: write a small completion record
        result = {
            "watcher_id": watcher_id,
            "claimed_from": str(src),
            "processing_as": str(dst),
            "completed_utc": utc_now_iso(),
            "result": "ok",
            "type": "noop",
        }

        # Move to completed
        done = completed / f"{src.name}.{watcher_id}.completed.json"
        write_json(done, result)

        # Clean up processing marker
        try:
            dst.unlink(missing_ok=True)
        except Exception:
            pass

        # Only one per cycle
        break


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watcher-id", required=True)
    ap.add_argument("--continuous", action="store_true", help="Run forever (Success v0 loop).")
    ap.add_argument("--opportunistic", action="store_true", help="Alias of continuous for now.")
    ap.add_argument("--poll-seconds", type=int, default=30)
    ap.add_argument("--config", default=None, help="Optional path to config YAML.")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[2]  # .../scripts/watcher/hjb_watcher.py -> repo root
    cfg = get_config(repo_root, args.config)

    paths = parse_paths(cfg)
    scratch_root = parse_scratch_root(cfg)

    # Fail-fast scratch contract
    ensure_scratch_contract(scratch_root)

    loop = args.continuous or args.opportunistic
    if not loop:
        # single cycle useful for testing
        run_once(
            watcher_id=args.watcher_id,
            state_root=paths["state_root"],
            flags_root=paths["flags_root"],
            logs_root=paths["logs_root"],
            poll_seconds=args.poll_seconds,
        )
        return 0

    print(f"[HJB] watcher_id={args.watcher_id} mode=continuous poll={args.poll_seconds}s")
    print(f"[HJB] state_root={paths['state_root']}")
    print(f"[HJB] flags_root={paths['flags_root']}")
    print(f"[HJB] logs_root={paths['logs_root']}")
    print(f"[HJB] scratch_root={scratch_root}")

    while True:
        run_once(
            watcher_id=args.watcher_id,
            state_root=paths["state_root"],
            flags_root=paths["flags_root"],
            logs_root=paths["logs_root"],
            poll_seconds=args.poll_seconds,
        )
        time.sleep(max(1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
