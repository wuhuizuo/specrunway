"""Model primitives: identifier grammar, path safety, structured errors, digests."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]*$\Z")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$\Z")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$\Z")
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$\Z")
GIT_HEX_RE = re.compile(r"^[0-9a-f]{40}$\Z")


class ValidationError(Exception):
    """One failed model check; ``code`` is a stable machine-readable key."""

    def __init__(self, code: str, message: str, *, path: str | None = None):
        self.code = code
        self.message = message
        self.path = path
        super().__init__(message)


class GroupedValidationError(ValidationError):
    """ValidationError carrying every failed check for one validate_* call."""

    def __init__(self, errors: list):
        first = errors[0]
        super().__init__(first["code"], first["message"], path=first.get("path"))
        self.errors: list = list(errors)


def collect_errors(fn, payload):  # type: ignore[no-untyped-def]
    """Run a validator and return ``(ok, errors)`` for batch-style callers."""
    try:
        return fn(payload)
    except ValidationError as exc:
        first = exc.message
        return False, [{"code": exc.code, "message": first, "path": exc.path}]  # type: ignore[list-item]


class ErrorCollector:
    """Gathers every failure so callers can fix all inputs at once."""

    def __init__(self) -> None:
        self.errors: list = []
        self._base = ""

    @property
    def base(self) -> str:
        return self._base

    def push_base(self, part: str) -> None:
        self._base = f"{self._base}/{part}" if self._base else part

    def pop_base(self) -> None:
        if not self._base:
            return
        self._base = self._base.rsplit("/", 1)[0] if "/" in self._base else ""

    def require(
        self,
        condition: bool,
        code: str,
        message: str,
    ) -> bool:
        if not condition:
            self.errors.append({"code": code, "message": message, "path": self._base or None})
        return condition

    def fail(self, code: str, message: str, stop: bool = True) -> bool:
        self.errors.append({"code": code, "message": message, "path": self._base or None})
        return not stop

    @property
    def ok(self) -> bool:
        return not self.errors


def error_report(errors: list) -> dict:
    return {"api_version": "hub/v1", "ok": False, "errors": list(errors)}


def is_uuid(value: object) -> bool:
    return isinstance(value, str) and bool(UUID_RE.match(value))


def is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and bool(SHA256_HEX_RE.match(value))


def is_task_id(value: object) -> bool:
    return isinstance(value, str) and bool(ID_RE.match(value))


def is_slug(value: object) -> bool:
    return isinstance(value, str) and bool(SLUG_RE.match(value))


def is_git_hex(value: object) -> bool:
    return isinstance(value, str) and bool(GIT_HEX_RE.match(value))


def is_safe_relpath(value: object) -> bool:
    """True when *value* is a relative, non-escaping, normalized POSIX path."""
    if not isinstance(value, str) or not value.strip():
        return False
    if value.startswith(("/", "\\")) or ":" in value or "\\" in value:
        return False
    try:
        pure = PurePosixPath(value)
    except (ValueError, MemoryError):  # sandboxed defense; variants are unlikely
        return False
    if pure.is_absolute():
        return False
    for part in pure.parts:
        if part in ("..", "."):
            return False
        if not part.strip():
            return False
    return True


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_digest(payload: dict) -> str:
    """Digest of a canonical (sorted-keys, compact) JSON rendering."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256_bytes(canonical.encode("utf-8"))


def strip_checkbox_markers(text: str) -> str:
    """Planning-digest input strips checkbox state, keeping task ID/text."""
    cleaned: list = []
    for line in text.splitlines():
        if line.startswith("- [ ] "):
            cleaned.append("- " + line[len("- [ ] ") :])
        elif line.startswith("- [x] "):
            cleaned.append("- " + line[len("- [x] ") :])
        else:
            cleaned.append(line)
    return "\n".join(cleaned)


def resolve_inside(base: Path, relative: str) -> Path:
    """Resolve *relative* under *base* and reject traversal outside it."""
    target = (base / relative).resolve()
    base_resolved = base.resolve()
    if not target.is_relative_to(base_resolved):
        raise ValidationError("path-traversal", f"escapes base path: {relative}")
    return target
