"""Trusted integration profile resolution and combined-matrix execution."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from specrunway.models.common import ValidationError, json_digest

DEFAULT_TIMEOUT_SECONDS = 900


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_integration_profile(config: dict, manifest: dict) -> dict:
    """Resolve the manifest's named profile from trusted control configuration."""
    profiles = config.get("integration_profiles") or {}
    name = str(manifest.get("integration_profile") or "")
    entry = profiles.get(name)
    if not isinstance(entry, dict):
        raise ValidationError(
            "integration-profile-missing",
            f"integration_profile {name!r} is not defined in local.yaml "
            "integration_profiles; refusing to run before any agent work",
        )
    command = entry.get("command")
    if not (isinstance(command, list) and command and all(isinstance(p, str) for p in command)):
        raise ValidationError(
            "integration-command", f"integration profile {name!r} has no argv command"
        )
    cwd_repo = entry.get("repo") or manifest["repo_order"][0]
    if cwd_repo not in manifest["repo_order"]:
        raise ValidationError(
            "integration-repo",
            f"integration profile {name!r} runs in {cwd_repo!r}, which is not in repo_order",
        )
    if cwd_repo not in (config.get("repos") or {}):
        raise ValidationError(
            "integration-repo",
            f"integration profile {name!r} runs in unconfigured repo {cwd_repo!r}",
        )
    timeout = entry.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS
    frozen = {
        "profile": name,
        "command": list(command),
        "cwd_repo": cwd_repo,
        "timeout_seconds": int(timeout),
    }
    frozen["config_digest"] = json_digest(frozen)
    return frozen


def build_matrix(state: dict, manifest: dict) -> list:
    """Accepted commit matrix for every participating repository."""
    results = state.get("results") or {}
    verification = state.get("verification") or {}
    rows = []
    for repo_id in manifest["repo_order"]:
        accepted = results.get(repo_id) or {}
        verified = verification.get(repo_id) or {}
        rows.append(
            {
                "repo_id": repo_id,
                "head_commit": accepted.get("head_commit"),
                "result_digest": accepted.get("result_digest"),
                "verification": verified.get("status"),
            }
        )
    return rows


def matrix_digest(rows: list) -> str:
    return json_digest({"matrix": rows})


def run_integration(integration: dict, run_dir: Path, rows: list, round_index: int) -> dict:
    """Execute the frozen integration argv against the matrix; persist a receipt."""
    run_dir = Path(run_dir)
    digest = matrix_digest(rows)
    round_dir = run_dir / "integration" / f"round-{round_index}"
    round_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = round_dir / "matrix.json"
    matrix_path.write_text(
        json.dumps({"matrix_digest": digest, "repos": rows}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    worktree = run_dir / "worktrees" / integration["cwd_repo"]
    if not worktree.is_dir():
        raise ValidationError(
            "integration-worktree",
            f"no worktree for integration repo {integration['cwd_repo']!r}",
        )
    log_path = run_dir / "logs" / "integration" / f"round-{round_index}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["SPECRUNWAY_MATRIX"] = str(matrix_path.resolve())
    for row in rows:
        key = "SPECRUNWAY_HEAD_" + row["repo_id"].upper().replace("-", "_")
        env[key] = str(row.get("head_commit") or "")
    started = time.monotonic()
    started_at = _now()
    status = "passed"
    reason = ""
    exit_code = 0
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {shlex.join(integration['command'])}\n")
        log.flush()
        try:
            done = subprocess.run(
                list(integration["command"]),
                cwd=str(worktree),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=float(integration["timeout_seconds"]),
                shell=False,
                check=False,
                stdin=subprocess.DEVNULL,
            )
            exit_code = done.returncode
            if exit_code != 0:
                status, reason = "failed", f"exit {exit_code}"
        except subprocess.TimeoutExpired:
            status, reason = "failed", f"killed after {integration['timeout_seconds']}s"
            exit_code = -1
        except OSError as exc:
            status, reason = "error", f"launch failed: {exc}"
            exit_code = -1
    return {
        "status": status,
        "exit_code": exit_code,
        "reason": reason,
        "command": list(integration["command"]),
        "cwd": str(worktree),
        "matrix_digest": digest,
        "heads": [row.get("head_commit") for row in rows],
        "matrix_ref": str(matrix_path),
        "round": int(round_index),
        "started_at": started_at,
        "finished_at": _now(),
        "duration_seconds": round(time.monotonic() - started, 3),
        "log_path": str(log_path.resolve()),
    }


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "build_matrix",
    "matrix_digest",
    "resolve_integration_profile",
    "run_integration",
]
