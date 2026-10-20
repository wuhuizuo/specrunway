"""Deterministic fake coding agent used by coordinator loop tests.

Invoked through the same argv shape as the real profile: the prompt file is
passed with ``--file <path>``. It edits an allowed path, commits with git,
and writes a contract-valid result.json next to the worktree.
"""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TASK_RE = re.compile(r"^- (T[A-Z0-9-]+)$", re.MULTILINE)


def _field(prompt: str, name: str) -> str:
    match = re.search(rf"^- {name}: (.+)$", prompt, re.MULTILINE)
    if not match:
        raise SystemExit(f"fake agent: prompt lacks {name}")
    return match.group(1).strip()


def main() -> int:
    argv = sys.argv[1:]
    if "--file" not in argv:
        raise SystemExit("fake agent: --file <prompt> is required")
    prompt_file = argv[argv.index("--file") + 1]
    prompt = Path(prompt_file).read_text(encoding="utf-8")
    execution_id = _field(prompt, "execution_id")
    base_oid = _field(prompt, "base_oid")
    repo_order = ast.literal_eval(_field(prompt, "repo_order"))
    allowed_paths = ast.literal_eval(_field(prompt, "allowed_paths"))
    repo_id = re.search(r"# Hub execution prompt: .* / (.+)$", prompt, re.MULTILINE).group(1)
    attempt = int(_field(prompt, "attempt"))
    tasks = TASK_RE.findall(prompt)

    root = Path.cwd()
    prefix = str(allowed_paths[0]).strip("/")
    target_dir = root / prefix
    target_dir.mkdir(parents=True, exist_ok=True)
    for task_id in tasks:
        (target_dir / f"fake_{task_id.lower()}.py").write_text(
            f"# implemented by the fake agent for {task_id}\nVALUE = {{'task': '{task_id}'}}\n",
            encoding="utf-8",
        )
    scenario = os.environ.get("HUB_FAKE_SCENARIO", "pass")
    fail_before = int(os.environ.get("HUB_FAKE_FAIL_BEFORE", "0"))
    failed_run = (
        scenario == "fail"
        or (scenario == "noop")
        or (scenario == "fail-until-pass" and attempt <= fail_before)
    )
    if scenario == "noop":
        # no commit at all: the next attempt produces the same head
        (target_dir / "test_fake_failure.py").write_text(
            "def test_never():\n    assert False, 'noop scenario failure'\n", encoding="utf-8"
        )
        head = base_oid
        changed = []
    else:
        failure_test = target_dir / "test_fake_failure.py"
        if failed_run:
            failure_test.write_text(
                f"def test_attempt_{attempt}():\n    assert False, 'attempt {attempt} fails'\n",
                encoding="utf-8",
            )
        elif failure_test.exists():
            failure_test.unlink()
        (root / "result.json").unlink(missing_ok=True)
        subprocess.run(["git", "add", "--", prefix], cwd=root, check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=fake-agent",
                "-c",
                "user.email=fake@example.org",
                "commit",
                "-m",
                f"fake agent: {repo_id} {' '.join(tasks)} attempt {attempt}",
            ],
            cwd=root,
            check=True,
            capture_output=True,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
    if scenario != "noop":
        changed = subprocess.run(
            ["git", "diff", "--name-only", f"{base_oid}..{head}"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
    record = {
        "api_version": "hub/v1",
        "execution_id": execution_id,
        "repo_id": repo_id,
        "attempt": attempt,
        "agent": "fake-agent",
        "head_commit": head,
        "base_commit": base_oid,
        "tasks": [{"task_id": t, "decision": "implemented", "notes": "fake"} for t in tasks],
        "changed_paths": sorted(changed),
        "tests_claimed": {"status": "failed" if failed_run else "passed"},
        "created_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
    }
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    record["result_digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    (root / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"fake agent finished {repo_id} {tasks} (order {repo_order})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
