"""Agent prompt assembly for a repository attempt (bounded context)."""

from __future__ import annotations

from pathlib import Path


def build_prompt(
    change_path: Path,
    manifest: dict,
    repo_entry: dict,
    snapshot: dict,
    rule_files: list,
    dependency_results: dict,
    prior_result: dict | None,
    attempt: int = 1,
) -> str:
    """Assemble the bounded agent prompt for one repo attempt.

    Passes the agent only: its tasks, the approved plan (proposal/design +
    its capability delta), organization rules (existing repo instruction
    files), dependency accepted results, and prior test feedback.
    """
    repo_id = repo_entry["repo_id"]
    lines: list = [
        f"# Hub execution prompt: {snapshot['change_id']} / {repo_id}",
        "",
        "## Your tasks",
        "",
    ]
    for task_id in repo_entry["task_ids"]:
        lines.append(f"- {task_id}")
    lines.append("")
    lines.append("## Task routing (frozen)")
    lines.append("")
    lines.append(f"- execution_id: {snapshot['execution_id']}")
    lines.append(f"- attempt: {int(attempt)}")
    lines.append(f"- repo_order: {manifest['repo_order']}")
    lines.append(f"- allowed_paths: {repo_entry['allowed_paths']}")
    lines.append(f"- test_profile: {repo_entry.get('test_profile', '')}")
    lines.append(f"- base_oid: {snapshot['repos'][repo_id]['base_oid']}")
    lines.append("")
    lines.append("## Approved plan")
    lines.append("")
    for name in ("proposal.md", "design.md"):
        plan_file = change_path / name
        if plan_file.is_file():
            lines.append(plan_file.read_text(encoding="utf-8").strip())
            lines.append("")
    delta_dir = change_path / "specs" / f"{repo_id}-delivery"
    if delta_dir.is_dir():
        delta = (delta_dir / "spec.md").read_text(encoding="utf-8")
        lines.append("## Capability delta")
        lines.append("")
        lines.append(delta.strip())
        lines.append("")
    if rule_files:
        lines.append("## Repository rules (existing instructions)")
        lines.append("")
        for found in rule_files:
            found_text = found.read_text(encoding="utf-8").strip()
            lines.append(found_text)
            lines.append("")
    if dependency_results:
        lines.append("## Dependency accepted results")
        lines.append("")
        for dep, row in dependency_results.items():
            lines.append(
                f"- {dep}: head {row.get('head_commit')} (result_digest {row.get('result_digest')}, passed: {row.get('passed')})"
            )
        lines.append("")
    if prior_result:
        lines.append("## Feedback on the previous attempt")
        lines.append("")
        lines.append(
            f"- previous head: {prior_result.get('head_commit')}, "
            f"result_digest {prior_result.get('result_digest')}"
        )
        lines.append("")
        lines.append("- Fix the previously rejected result; keep allowed paths only.")
        lines.append("")
    lines.append("## Output contract")
    lines.append("")
    lines.append("1. Implement every listed task inside the current working directory.")
    lines.append("2. Commit changes (git commit) so the head commit contains the work.")
    lines.append(
        "3. Write a JSON file result.json in the working directory root with "
        "api_version hub/v1, execution_id, repo_id, attempt, agent name, "
        "head_commit, base_commit, tasks (task_id, decision, notes), "
        "changed_paths (repo-relative), result_digest (sha256 of payload minus "
        "result_digest), tests_claimed {status, command}, and created_at ISO string."
    )
    lines.append(
        "4. Do not touch paths outside the allowed_paths list; tests and commits run by the coordinator count, not your prose."
    )
    return "\n".join(lines) + "\n"


__all__ = ["build_prompt"]
