"""``hub doctor``: machine-checked wiring report for a local control checkout."""

from __future__ import annotations

from pathlib import Path

from . import __version__
from .models import ValidationError, load_local_config, validate_checkout_wiring

CONTROL_CONFIG = "local.yaml"


def find_control_root(start: Path) -> Path | None:
    """Walk upward from *start* looking for the machine-only ``local.yaml``."""
    probe = start.resolve()
    for candidate in (probe, *probe.parents):
        if (candidate / CONTROL_CONFIG).is_file():
            return candidate
    return None


def run_doctor(root_dir: str | None = None) -> dict:
    """Collect deterministic wiring findings for the control checkout."""
    warnings: list = []
    errors: list = []
    findings: list = []
    data = {"hub_version": __version__, "control_root": None}

    root = Path(root_dir).resolve() if root_dir else find_control_root(Path.cwd())
    if root is None:
        findings.append(
            _finding(
                "control-checkout",
                "error",
                f"no {CONTROL_CONFIG} found from {Path.cwd()} upward; "
                "run hub from the control checkout that carries it",
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

    findings.append(_finding("local-yaml", "ok", "parsed and valid (hub/v1 shapes)"))
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

    findings.append(_finding("max_workers", "ok", "v1 runs one execution per checkout"))
    return _report(findings, warnings, errors, data, ok=not errors)


def _finding(check: str, severity: str, message: str) -> dict:
    return {"check": check, "severity": severity, "message": message}


def _report(findings: list, warnings: list, errors: list, data: dict, ok: bool = False) -> dict:
    data["findings"] = findings
    return {
        "api_version": "hub/v1",
        "action": "doctor",
        "ok": ok,
        "data": data,
        "warnings": warnings,
        "errors": list(errors),
    }
