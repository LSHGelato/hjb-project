#!/usr/bin/env python3
"""
HJB Watcher (Success v0)

Goals:
- Write a heartbeat JSON file to NAS state_root
- Claim tasks from flags/pending via atomic rename to flags/processing
- Complete tasks by moving to flags/completed
- Support opportunistic mode: short poll intervals, check if OrionMX is busy before claiming
- Support one-task-and-exit mode: process one task then cleanly exit
- Fail fast if scratch root or NAS state paths are missing

Design notes:
- Intentionally minimal. No OCR. No MySQL. No MediaWiki.
- Uses config/config.yaml if present, else falls back to config.example.yaml.
- Opportunistic mode: 10-second poll, check if orionmx_* watchers have processing tasks
- One-task mode: claim one task, process it, then exit cleanly
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import traceback
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

import yaml


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


TASK_SCHEMA_V1 = "hjb.task.v1"
TASK_RESULT_SCHEMA_V1 = "hjb.task_result.v1"
TASK_ERROR_SCHEMA_V1 = "hjb.task_error.v1"


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
    # Use a unique temp name to avoid SMB/AV/file-indexer collisions.
    # Also retry briefly because NAS writes can be transiently locked.
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{int(time.time()*1000)}.tmp")
    txt = json.dumps(payload, indent=2, sort_keys=True)
    for attempt in range(1, 6):
        try:
            tmp.write_text(txt, encoding="utf-8")
            tmp.replace(path)
            return
        except PermissionError:
            # Back off and retry (common on SMB shares)
            time.sleep(0.15 * attempt)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
    # If we get here, we failed after retries.
    raise PermissionError(f"Failed to write JSON (retries exhausted): {path}")

def heartbeat_path(state_root: Path, watcher_id: str) -> Path:
    return state_root / f"watcher_heartbeat_{watcher_id}.json"

def acquire_single_instance_lock(state_root: Path, watcher_id: str) -> Path:
    """
    Enforce one active watcher per watcher_id across the share.
    Uses atomic directory creation on SMB/NTFS:
      state_root/locks/watcher_<id>.lock/
        owner.json
    If the lock already exists, we exit immediately.
    """
    locks_root = state_root / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)

    lock_dir = locks_root / f"watcher_{watcher_id}.lock"
    owner_path = lock_dir / "owner.json"

    try:
        lock_dir.mkdir()  # atomic: fails if exists
    except FileExistsError:
        raise SystemExit(
            f"Watcher lock already held: {lock_dir}. "
            f"Another watcher instance for '{watcher_id}' is running (or a stale lock exists)."
        )

    # Best-effort: record owner information (not required for locking)
    try:
        owner = {
            "watcher_id": watcher_id,
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "utc_started": utc_now_iso(),
            "utc_last_seen": utc_now_iso(),
        }
        owner_path.write_text(json.dumps(owner, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        pass

    return lock_dir

def update_lock_owner(lock_dir: Path, watcher_id: str) -> None:
    """
    Best-effort liveness update under the lock directory.
    This gives the supervisor a reliable PID even if heartbeat writes are flaky.
    """
    try:
        owner_path = lock_dir / "owner.json"
        owner = {
            "watcher_id": watcher_id,
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "executable": sys.executable,
            "utc_last_seen": utc_now_iso(),
        }
        owner_path.write_text(json.dumps(owner, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        pass

def release_single_instance_lock(lock_dir: Optional[Path]) -> None:
    if not lock_dir:
        return
    try:
        # Remove owner.json first if present
        owner_path = lock_dir / "owner.json"
        if owner_path.exists():
            owner_path.unlink()
        lock_dir.rmdir()
    except Exception:
        # Do not fail shutdown on cleanup issues
        pass

def parse_paths(cfg: Dict[str, Any]) -> Dict[str, Path]:
    """
    Accepts either:
    - cfg["paths"]["state_root"] style, OR
    - cfg["storage"]["nas_root"] + cfg["storage"]["state_dir"] (construct state_root from both)
    """
    paths = cfg.get("paths", {})
    storage = cfg.get("storage", {})
    if not isinstance(paths, dict):
        paths = {}
    if not isinstance(storage, dict):
        storage = {}

    def pick(key: str) -> Optional[str]:
        # Try paths first, then top-level cfg, then storage
        v = paths.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        v2 = cfg.get(key)
        if isinstance(v2, str) and v2.strip():
            return v2.strip()
        v3 = storage.get(key)
        if isinstance(v3, str) and v3.strip():
            return v3.strip()
        return None

    # Try explicit state_root first
    state_root_s = pick("state_root")
    
    # If not found, try nas_root + state_dir
    if not state_root_s:
        nas_root_s = pick("nas_root")
        state_dir_s = pick("state_dir")
        if nas_root_s and state_dir_s:
            state_root_s = str(Path(nas_root_s) / state_dir_s)
    
    if not state_root_s:
        raise KeyError("Missing state_root (expected cfg.state_root, cfg.paths.state_root, or cfg.storage.nas_root + cfg.storage.state_dir)")

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


def is_orionmx_busy(flags_root: Path) -> bool:
    """
    Check if any orionmx_* watcher has tasks in processing.
    Returns True if at least one orionmx_* task is being processed.
    """
    processing = flags_root / "processing"
    if not processing.exists():
        return False
    
    for task_file in processing.glob("*"):
        if task_file.is_file() and "orionmx_" in task_file.name:
            return True
    return False


def execute_manifest_task(
    manifest: Dict[str, Any],
    task_id: str,
    task_type: str,
    attempt: int,
    state_root: Path,
    flags_root: Path,
    watcher_id: str,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Execute a manifest-driven JSON flag.
    Returns: (outputs, metrics)
    """
    if task_type == "noop":
        outdir = (flags_root / "completed" / task_id / "noop")
        outdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        marker = outdir / f"noop_{task_id}_{ts}.txt"
        marker.write_text("noop ok\n", encoding="utf-8")
        return [str(marker)], {"noop": True}

    if task_type == "stage1.inventory":
        return task_stage1_inventory(manifest, task_id, flags_root)

    if task_type == "stage1.ia_download":
        return task_stage1_ia_download(manifest, task_id, flags_root)
    
    raise ValueError(f"Unknown task_type: {task_type}")


def _matches_any_glob(path_str: str, globs: List[str]) -> bool:
    """
    Windows-friendly glob matching against forward-slash-normalized paths.
    """
    from fnmatch import fnmatch
    norm = path_str.replace("\\", "/")
    return any(fnmatch(norm, g) for g in globs)


def task_stage1_inventory(manifest: Dict[str, Any], task_id: str, flags_root: Path) -> Tuple[List[str], Dict[str, Any]]:
    payload = manifest.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object (dict)")

    roots = payload.get("roots")
    if not (isinstance(roots, list) and all(isinstance(x, str) and x.strip() for x in roots)):
        raise KeyError("payload.roots must be a list of UNC path strings")

    include_sha256 = bool(payload.get("include_sha256", False))

    include_globs = payload.get("include_globs")
    if include_globs is not None:
        if not (isinstance(include_globs, list) and all(isinstance(x, str) for x in include_globs)):
            raise ValueError("payload.include_globs must be a list of strings")

    exclude_globs = payload.get("exclude_globs")
    if exclude_globs is not None:
        if not (isinstance(exclude_globs, list) and all(isinstance(x, str) for x in exclude_globs)):
            raise ValueError("payload.exclude_globs must be a list of strings")

    # Safety brakes (defaults ON)
    # - set max_files=0 to disable
    # - set max_seconds=0 to disable
    max_files = payload.get("max_files", 100000)
    max_seconds = payload.get("max_seconds", 1800)  # 30 minutes

    if max_files is None:
        max_files = 100000
    if max_seconds is None:
        max_seconds = 1800

    if not isinstance(max_files, int) or max_files < 0:
        raise ValueError("payload.max_files must be an int >= 0 (0 disables the limit)")
    if not isinstance(max_seconds, int) or max_seconds < 0:
        raise ValueError("payload.max_seconds must be an int >= 0 (0 disables the limit)")

    started = time.monotonic()
    stopped_reason: Optional[str] = None

    outdir = (flags_root / "completed" / task_id / "inventory")
    outdir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_csv = outdir / f"inventory_{task_id}_{ts}.csv"

    fields = ["root", "relpath", "fullpath", "size_bytes", "mtime_utc"]
    if include_sha256:
        fields.append("sha256")

    files_seen = 0
    bytes_seen = 0

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()

        for root_s in roots:
            root = Path(root_s)
            if not root.exists():
                raise FileNotFoundError(f"Inventory root does not exist: {root}")

            for dirpath, dirnames, filenames in os.walk(str(root)):
                # Safety brake: time-based (checked per directory)
                if max_seconds and (time.monotonic() - started) > max_seconds:
                    stopped_reason = f"max_seconds_exceeded({max_seconds})"
                    break

                # Prune excluded directories so we do not traverse them at all
                pruned: List[str] = []
                for d in dirnames:
                    d_full = str(Path(dirpath) / d)

                    # Always prune flag archives
                    if "\\flags\\completed\\" in d_full or "\\flags\\failed\\" in d_full:
                        continue

                    # Operator exclusions prune traversal
                    if exclude_globs and _matches_any_glob(d_full, exclude_globs):
                        continue

                    pruned.append(d)
                dirnames[:] = pruned

                for name in filenames:
                    # Safety brake: count-based
                    if max_files and files_seen >= max_files:
                        stopped_reason = f"max_files_reached({max_files})"
                        break

                    full = Path(dirpath) / name

                    # Normalize once for matching
                    full_str = str(full)

                    # Hard default exclusions (always on)
                    if "\\flags\\completed\\" in full_str or "\\flags\\failed\\" in full_str:
                        continue

                    # Operator-specified exclusions
                    if exclude_globs and _matches_any_glob(full_str, exclude_globs):
                        continue

                    # Operator-specified inclusions
                    if include_globs and not _matches_any_glob(full_str, include_globs):
                        continue

                    try:
                        st = full.stat()
                    except OSError:
                        continue

                    files_seen += 1
                    bytes_seen += int(st.st_size)
                    mtime_utc = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
                    try:
                        rel = str(full.relative_to(root))
                    except Exception:
                        rel = ""

                    row = {
                        "root": str(root),
                        "relpath": rel,
                        "fullpath": str(full),
                        "size_bytes": int(st.st_size),
                        "mtime_utc": mtime_utc,
                    }

                    if include_sha256:
                        try:
                            import hashlib
                            h = hashlib.sha256()
                            with full.open("rb") as rf:
                                for chunk in iter(lambda: rf.read(1024 * 1024), b""):
                                    h.update(chunk)
                            row["sha256"] = h.hexdigest()
                        except OSError:
                            row["sha256"] = ""

                    w.writerow(row)

                if stopped_reason:
                    break

            if stopped_reason:
                break

    return [str(out_csv)], {
        "files_seen": files_seen,
        "bytes_seen": bytes_seen,
        "include_sha256": include_sha256,
        "max_files": max_files,
        "max_seconds": max_seconds,
        "stopped_reason": stopped_reason,
        "elapsed_seconds": int(time.monotonic() - started),
    }

import subprocess

def task_stage1_ia_download(manifest: Dict[str, Any], task_id: str, flags_root: Path) -> Tuple[List[str], Dict[str, Any]]:
    payload = manifest.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object (dict)")

    list_file = payload.get("list_file")
    if not (isinstance(list_file, str) and list_file.strip()):
        raise KeyError("payload.list_file must be a string path")

    output_root = payload.get("output_root")
    include_ocr = bool(payload.get("include_ocr", False))
    max_items = int(payload.get("max_items", 0) or 0)
    dry_run = bool(payload.get("dry_run", False))

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "stage1" / "ia_acquire.py"
    if not script.is_file():
        raise FileNotFoundError(f"Missing acquisition script: {script}")

    args = [sys.executable, str(script), "--list-file", str(list_file)]
    if isinstance(output_root, str) and output_root.strip():
        args += ["--output-root", output_root.strip()]
    if include_ocr:
        args.append("--include-ocr")
    if max_items > 0:
        args += ["--max-items", str(max_items)]
    if dry_run:
        args.append("--dry-run")

    # Run in repo root so relative paths behave
    proc = subprocess.run(args, cwd=str(repo_root), capture_output=True, text=True)

    # Store stdout/stderr into completed folder for auditability
    outdir = (flags_root / "completed" / task_id / "stage1_ia_download")
    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stdout_path = outdir / f"ia_acquire_{task_id}_{ts}.stdout.txt"
    stderr_path = outdir / f"ia_acquire_{task_id}_{ts}.stderr.txt"
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")

    if proc.returncode != 0:
        raise RuntimeError(f"ia_acquire failed (exit={proc.returncode}). See: {stdout_path} / {stderr_path}")

    return [str(stdout_path), str(stderr_path)], {
        "include_ocr": include_ocr,
        "max_items": max_items,
        "dry_run": dry_run,
        "list_file": list_file,
        "output_root": output_root,
        "exit_code": proc.returncode,
    }

def run_once(
    watcher_id: str,
    state_root: Path,
    flags_root: Path,
    logs_root: Path,
    poll_seconds: int,
    opportunistic: bool = False,
) -> bool:
    """
    Run one cycle of the watcher.
    
    Returns True if a task was processed (for one-task-and-exit mode).
    Returns False if no task was processed.
    """
    pending = flags_root / "pending"
    processing = flags_root / "processing"
    completed = flags_root / "completed"
    failed = flags_root / "failed"
    
    # Ensure required directories exist on NAS
    for p, label in [
        (state_root, "state_root"),
        (flags_root, "flags_root"),
        (pending, "flags/pending"),
        (processing, "flags/processing"),
        (completed, "flags/completed"),
        (failed, "flags/failed"),
        (logs_root, "logs_root"),
    ]:
        require_dir(p, label)

    # Heartbeat
    hb = heartbeat_path(state_root, watcher_id)
    hb_payload = {
        "watcher_id": watcher_id,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "executable": sys.executable,
        "argv": sys.argv,
        "utc": utc_now_iso(),
        "mode": "success_v0",
        "poll_seconds": poll_seconds,
        "status": "running",
        "opportunistic": opportunistic,
    }
    try:
        write_json(hb, hb_payload)
    except Exception:
        # Heartbeat is informational; do not crash if SMB transiently locks the file.
        pass
    
    # In opportunistic mode: check if OrionMX watchers are busy
    # Only claim a task if OrionMX has processing tasks
    if opportunistic:
        if not is_orionmx_busy(flags_root):
            # OrionMX is idle; don't hog resources
            return False
        
    # Try to claim one manifest-driven JSON task
    json_candidates = sorted([p for p in pending.glob("*.json") if p.is_file()])
    for src in json_candidates[:1]:
        dst = processing / f"{src.name}.{watcher_id}.processing"
        if not atomic_rename(src, dst):
            continue

        task_processed = False
        started_utc = utc_now_iso()
        started_ts = time.time()
        try:
            manifest = json.loads(dst.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("Task manifest JSON must be an object (dict)")

            schema = manifest.get("schema")
            if schema and schema != TASK_SCHEMA_V1:
                raise ValueError(f"Unsupported task schema: {schema}")

            task_type = manifest.get("task_type")
            if not (isinstance(task_type, str) and task_type.strip()):
                raise KeyError("Missing required task_type (string)")
            task_type = task_type.strip()

            task_id = manifest.get("task_id")
            if not (isinstance(task_id, str) and task_id.strip()):
                # fallback: derive from filename + timestamp
                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                task_id = f"{ts}_{dst.stem}"
            task_id = task_id.strip()

            attempt = manifest.get("attempt")
            attempt_i = attempt if isinstance(attempt, int) and attempt >= 1 else 1

            # Execute
            outputs, metrics = execute_manifest_task(
                manifest=manifest,
                task_id=task_id,
                task_type=task_type,
                attempt=attempt_i,
                state_root=state_root,
                flags_root=flags_root,
                watcher_id=watcher_id,
            )

            # Archive manifest + write result under flags/completed/<task_id>/
            outdir = completed / task_id
            outdir.mkdir(parents=True, exist_ok=True)

            (outdir / f"{task_id}.{watcher_id}.manifest.json").write_text(
                dst.read_text(encoding="utf-8"), encoding="utf-8"
            )

            ended_utc = utc_now_iso()
            elapsed_seconds = int(time.time() - started_ts)
            ts2 = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            result_path = outdir / f"{task_id}.{watcher_id}.{ts2}.result.json"
            write_json(result_path, {
                "schema": TASK_RESULT_SCHEMA_V1,
                "task_id": task_id,
                "task_type": task_type,
                "attempt": attempt_i,
                "watcher_id": watcher_id,
                "hostname": socket.gethostname(),
                "pid": os.getpid(),
                "started_utc": started_utc,
                "ended_utc": ended_utc,
                "duration_seconds": elapsed_seconds,
                "status": "ok",
                "outputs": outputs,
                "metrics": metrics,
            })

            # Clean up processing marker (preserve evidence by default as .done)
            try:
                dst.replace(outdir / f"{src.name}.{watcher_id}.done")
            except Exception:
                pass
            
            task_processed = True

        except Exception as ex:
            # Write error under flags/failed/<task_id-or-derived>/
            ts_fail = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            fallback_id = f"{ts_fail}_{dst.stem}"
            try:
                maybe = json.loads(dst.read_text(encoding="utf-8"))
                if isinstance(maybe, dict) and isinstance(maybe.get("task_id"), str) and maybe.get("task_id").strip():
                    fallback_id = maybe["task_id"].strip()
            except Exception:
                pass

            errdir = failed / fallback_id
            errdir.mkdir(parents=True, exist_ok=True)

            try:
                (errdir / f"{fallback_id}.{watcher_id}.manifest.json").write_text(
                    dst.read_text(encoding="utf-8"), encoding="utf-8"
                )
            except Exception:
                pass

            ended_utc = utc_now_iso()
            elapsed_seconds = int(time.time() - started_ts)
            err_path = errdir / f"{fallback_id}.{watcher_id}.{ts_fail}.error.json"
            write_json(err_path, {
                "schema": TASK_ERROR_SCHEMA_V1,
                "task_id": fallback_id,
                "watcher_id": watcher_id,
                "hostname": socket.gethostname(),
                "pid": os.getpid(),
                "started_utc": started_utc,
                "ended_utc": ended_utc,
                "duration_seconds": elapsed_seconds,
                "status": "error",
                "error_type": type(ex).__name__,
                "error": str(ex),
                "traceback": traceback.format_exc(limit=50),
            })

            try:
                dst.replace(errdir / f"{src.name}.{watcher_id}.failed")
            except Exception:
                pass
        
        return task_processed
    
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watcher-id", required=False)
    ap.add_argument("--continuous", action="store_true", help="Run forever (Success v0 loop).")
    ap.add_argument("--opportunistic", action="store_true", help="Opportunistic mode: short poll, check OrionMX busy.")
    ap.add_argument("--one-task-and-exit", action="store_true", help="Process one task then exit.")
    ap.add_argument("--poll-seconds", type=int, default=30)
    ap.add_argument("--config", default=None, help="Optional path to config YAML.")
    args = ap.parse_args()

    # Resolve watcher id:
    # - prefer CLI --watcher-id
    # - else fall back to machine-level env var HJB_WATCHER_ID
    watcher_id = args.watcher_id
    if not watcher_id:
        watcher_id = os.environ.get("HJB_WATCHER_ID")
    if not watcher_id or not str(watcher_id).strip():
        raise SystemExit("Missing watcher id: supply --watcher-id or set system env var HJB_WATCHER_ID")
    watcher_id = str(watcher_id).strip()

    repo_root = Path(__file__).resolve().parents[2]  # .../scripts/watcher/hjb_watcher.py -> repo root
    cfg = get_config(repo_root, args.config)

    paths = parse_paths(cfg)
    scratch_root = parse_scratch_root(cfg)

    # Fail-fast scratch contract
    ensure_scratch_contract(scratch_root)

    # Enforce one active watcher per watcher_id (prevents duplicate instances)
    lock_dir: Optional[Path] = None
    try:
        lock_dir = acquire_single_instance_lock(paths["state_root"], watcher_id)
    except SystemExit:
        raise
    except Exception as ex:
        raise SystemExit(f"Failed to acquire watcher lock for '{watcher_id}': {ex}")

    # Determine poll interval based on mode
    poll_seconds = args.poll_seconds
    if args.opportunistic:
        poll_seconds = 10  # Hungry polling for opportunistic mode

    # Determine loop behavior
    one_task_mode = args.one_task_and_exit
    continuous_mode = args.continuous or args.opportunistic

    if not continuous_mode:
        # Single cycle useful for testing
        run_once(
            watcher_id=watcher_id,
            state_root=paths["state_root"],
            flags_root=paths["flags_root"],
            logs_root=paths["logs_root"],
            poll_seconds=poll_seconds,
            opportunistic=args.opportunistic,
        )
        return 0

    mode_label = "opportunistic" if args.opportunistic else "continuous"
    print(f"[HJB] watcher_id={watcher_id} mode={mode_label} one_task={one_task_mode} poll={poll_seconds}s")
    print(f"[HJB] state_root={paths['state_root']}")
    print(f"[HJB] flags_root={paths['flags_root']}")
    print(f"[HJB] logs_root={paths['logs_root']}")
    print(f"[HJB] scratch_root={scratch_root}")

    try:
        while True:
            if lock_dir is not None:
                update_lock_owner(lock_dir, watcher_id)
            
            task_processed = run_once(
                watcher_id=watcher_id,
                state_root=paths["state_root"],
                flags_root=paths["flags_root"],
                logs_root=paths["logs_root"],
                poll_seconds=poll_seconds,
                opportunistic=args.opportunistic,
            )
            
            # If one-task mode and task was processed, exit cleanly
            if one_task_mode and task_processed:
                print(f"[HJB] One-task mode: task processed, exiting.")
                return 0
            
            time.sleep(max(1, poll_seconds))
    finally:
        release_single_instance_lock(lock_dir)

if __name__ == "__main__":
    raise SystemExit(main())
