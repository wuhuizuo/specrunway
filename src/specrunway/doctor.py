"""``specrunway doctor``: machine-checked wiring report for a local control checkout."""

from __future__ import annotations

import tempfile
from pathlib import Path
from shutil import which

from . import __version__
from .models import ValidationError, load_local_config, validate_checkout_wiring

CONTROL_CONFIG = "local.yaml"

#: A preflight is bounded so `doctor` never waits for real repository work.
AGENT_PROBE_TIMEOUT_SECONDS = 60.0
AGENT_PROBE_SESSION_ID = "ses_srdoctorprobe"
AGENT_PROBE_PROMPT = (
    "Answer with the single word OK. Do not read, create, or modify files; "
    "this is a bounded availability check.\n"
)


def find_control_root(start: Path) -> Path | None:
    """Walk upward from *start* looking for the machine-only ``local.yaml``."""
    probe = start.resolve()
    for candidate in (probe, *probe.parents):
        if (candidate / CONTROL_CONFIG).is_file():
            return candidate
    return None


def run_doctor(root_dir: str | None = None, *, probe_agent: bool = True) -> dict:
    """Collect deterministic wiring findings for the control checkout.

    ``probe_agent`` runs the bounded coding-agent preflight; bootstrap calls
    pass ``False`` because it checks wiring only.
    """
    warnings: list = []
    errors: list = []
    findings: list = []
    data = {"specrunway_version": __version__, "control_root": None}

    root = Path(root_dir).resolve() if root_dir else find_control_root(Path.cwd())
    if root is None:
        findings.append(
            _finding(
                "control-checkout",
                "error",
                f"no {CONTROL_CONFIG} found from {Path.cwd()} upward; "
                "run specrunway from the control checkout that carries it",
            )
        )
        errors.append("no-control-checkout")
        return _report(findings, warnings, errors, data)

    data["control_root"] = str(root)
    config_path = root / CONTROL_CONFIG
    if not config_path.is_file():
        findings.append(
            _finding(
                "local-yaml",
                "error",
                f"{CONTROL_CONFIG} not found in {root} (explicit root must be a control checkout)",
            )
        )
        errors.append("local-yaml")
        return _report(findings, warnings, errors, data)

    try:
        config = load_local_config(root)
    except ValidationError as exc:
        detail = getattr(exc, "errors", None) or [{"code": exc.code, "message": exc.message}]
        for row in detail:
            findings.append(
                _finding(
                    "local-yaml",
                    "error",
                    f"[{row.get('code')}] {row.get('message')}"
                    + (f" (at {row['path']})" if row.get("path") else ""),
                )
            )
        errors.append("local-yaml")
        return _report(findings, warnings, errors, data)
    except FileNotFoundError:
        findings.append(_finding("local-yaml", "error", f"missing {config_path}"))
        errors.append("local-yaml")
        return _report(findings, warnings, errors, data)

    findings.append(_finding("local-yaml", "ok", "parsed and valid (specrunway/v1 shapes)"))
    findings.append(_finding("store.id", "ok", f"declared store id: {config['store']['id']}"))
    findings.append(_finding("store.path", "ok", config["store"]["path"]))
    data["store"] = {"id": config["store"]["id"], "path": config["store"]["path"]}

    agent_profile = config["agent_profile"]
    findings.append(_finding("agent-profile", "ok", f"declared: {agent_profile}"))
    data["agent_profile"] = agent_profile

    wiring_rows = validate_checkout_wiring(config)
    repo_rows: dict = {}
    store_rows: list = []
    for row in wiring_rows:
        path = row.get("path") or ""
        if path.startswith("repos/"):
            repo_key = path.split("/")[1]
            repo_rows.setdefault(repo_key, []).append(row)
        else:
            store_rows.append(row)
    for store_row in store_rows:
        findings.append(
            _finding("store.path", "error", f"[{store_row['code']}] {store_row['message']}")
        )
    for repo_id in sorted(config["repos"]):
        rows = repo_rows.get(repo_id, [])
        if not rows:
            findings.append(_finding(f"repo:{repo_id}", "ok", config["repos"][repo_id]["path"]))
            continue
        findings.append(
            _finding(
                f"repo:{repo_id}",
                "error",
                "; ".join(f"[{row['code']}] {row['path']}" for row in rows)
                + f"; {config['repos'][repo_id]['path']}",
            )
        )
    data["repos"] = {
        repo_id: {"path": config["repos"][repo_id]["path"]}
        for repo_id in sorted(config["repos"])
    }
    errors.extend(row["code"] for row in wiring_rows)

    if probe_agent:
        agent = probe_agent_preflight(agent_profile)
        data["agent"] = agent
        if agent["ok"]:
            findings.append(
                _finding(
                    "agent-preflight",
                    "ok",
                    f"{agent['profile']} resolved to {agent['binary']} and answered "
                    f"in {agent['duration_seconds']}s",
                )
            )
        else:
            detail = f"{agent['profile']} cannot answer: {agent['reason'] or agent['status']}"
            if agent.get("binary"):
                detail += f" (binary {agent['binary']})"
            elif agent.get("binary") is None and agent["status"] == "missing-binary":
                detail += " (binary not found on PATH)"
            if agent.get("log_tail"):
                detail += f"; log tail: {agent['log_tail']}"
            findings.append(_finding("agent-preflight", "error", detail))
            errors.append("agent-preflight")

    findings.append(_finding("max_workers", "ok", "v1 runs one execution per checkout"))
    return _report(findings, warnings, errors, data, ok=not errors)


def probe_agent_preflight(
    profile_name: str, timeout_seconds: float = AGENT_PROBE_TIMEOUT_SECONDS
) -> dict:
    """Resolve the coding agent and check it can answer inside a disposable cwd.

    The probe never runs in a business checkout: the prompt and the agent's
    working directory live in a temporary directory that is removed afterwards.
    """
    from .launcher import resolve_profile, run_agent

    result = {
        "profile": profile_name,
        "binary": None,
        "ok": False,
        "status": "not-run",
        "reason": "",
        "exit_code": None,
        "duration_seconds": 0.0,
        "log_tail": "",
    }
    try:
        profile = resolve_profile(profile_name)
    except ValidationError as exc:
        result.update(
            status="unknown-profile",
            reason=f"[{getattr(exc, 'code', 'profile-unknown')}] {exc}",
        )
        return result
    if not profile.argv:
        result.update(status="missing-binary", reason="agent profile has no argv")
        return result
    executable = profile.argv[0]
    binary = which(executable)
    result["binary"] = binary
    if binary is None:
        result.update(
            status="missing-binary",
            reason=f"agent executable {executable!r} is not on PATH",
        )
        return result

    with tempfile.TemporaryDirectory(prefix="specrunway-agent-probe-") as tmp:
        probe_root = Path(tmp)
        prompt_file = probe_root / "prompt.md"
        prompt_file.write_text(AGENT_PROBE_PROMPT, encoding="utf-8")
        try:
            outcome = run_agent(
                profile,
                cwd=probe_root,
                prompt_file=prompt_file,
                log_dir=probe_root,
                timeout_seconds=timeout_seconds,
                # A dedicated throwaway conversation: the probe never reuses a
                # change's session, so stale context cannot answer for the agent.
                session_id=AGENT_PROBE_SESSION_ID,
            )
        except ValidationError as exc:
            result.update(
                status="launch-failed",
                reason=f"[{getattr(exc, 'code', 'launch-failed')}] {exc}",
            )
            return result
        tail = _log_tail(Path(outcome.get("log_path") or ""))

    result.update(
        status=outcome["status"],
        ok=outcome["status"] == "completed",
        reason=outcome.reason,
        exit_code=outcome.get("exit_code"),
        duration_seconds=outcome.get("duration_seconds", 0.0),
        log_tail=tail,
    )
    return result


def _log_tail(path: Path, lines: int = 3) -> str:
    """Last non-empty log lines, bounded for a finding message."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    return " | ".join(rows[-lines:])[:300]


def _finding(check: str, severity: str, message: str) -> dict:
    return {"check": check, "severity": severity, "message": message}


def _report(findings: list, warnings: list, errors: list, data: dict, ok: bool = False) -> dict:
    data["findings"] = findings
    return {
        "api_version": "specrunway/v1",
        "action": "doctor",
        "ok": ok,
        "data": data,
        "warnings": warnings,
        "errors": list(errors),
    }
