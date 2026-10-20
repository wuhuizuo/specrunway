"""Remote identity normalization for ``remote_identity`` checks."""

from __future__ import annotations

from urllib.parse import urlparse

_PREFIX_HOSTS = {"github": "github.com", "gitlab": "gitlab.com", "bitbucket": "bitbucket.org"}


def normalize_remote_url(url: str) -> tuple:
    """Return ``(host, path)`` for common URL/scp-style Git remotes."""
    url = url.strip()
    if "://" in url:
        parsed = urlparse(url)
        host = parsed.netloc
        if "@" in host:
            host = host.rsplit("@", 1)[1]
        path = parsed.path.strip("/")
        return host.rstrip(":"), path
    scp_like = url
    scp_like = scp_like.removeprefix("ssh://")
    if scp_like.lower().startswith(("git@",)):
        _user, _, rest = scp_like.partition("@")
        host, _, path = rest.partition(":")
        return host, path.strip("/").strip()
    # Transport shorthand such as ``github:owner/repo-name``.
    shorthand, _, rest = url.partition(":")
    if shorthand in _PREFIX_HOSTS and rest.startswith("/"):
        return _PREFIX_HOSTS[shorthand], rest.strip("/")
    if shorthand in _PREFIX_HOSTS:
        return _PREFIX_HOSTS[shorthand], rest.strip("/")
    return "", url.strip("/")


def normalize_identity(identity: str) -> tuple:
    """Return ``(host, path)`` from a remote_identity declaration.

    Supported forms: transport shorthands (``github:owner/repo-name``) and
    full HTTPS/SSH URLs (``https://host/path/repo.git``, ``git@host:owner/repo.git``).
    """
    identity = identity.strip()
    shorthand, _, rest = identity.partition(":")
    if shorthand in _PREFIX_HOSTS and rest.strip("/"):
        host = _PREFIX_HOSTS[shorthand]
        path = rest.strip("/")
        path = path.removeprefix("//")
        return host, path
    if (
        identity.startswith(("http://", "https://", "ssh://"))
        or "@" in identity.split("/", 1)[0]
        and ":" not in identity.split("/", 1)[0]
    ):
        return normalize_remote_url(identity)
    # Bare ``host:owner/repo-name`` scp style declaration (user may prefix host).
    host, _, path = identity.partition(":")
    return host.rsplit("@", 1)[-1].strip(), path.strip("/")


def remote_matches(identity: str, url: str) -> bool:
    """True when *url* points at the same host and repository as *identity*."""
    id_host, id_path = normalize_identity(identity)
    url_host, url_path = normalize_remote_url(url)
    if not id_host or not url_host or id_host.lower() != url_host.lower():
        return _prefix_alias_match(id_host, id_path, url_host, url_path)
    return _path_match(id_path, url_path)


def _prefix_alias_match(id_host, id_path, url_host, url_path) -> bool:
    # ``github:``-style identity and full URL remotes normalize to distinct
    # host spellings (for example ``ssh.git@github.com``); accept suffix match.
    if url_host.split(".")[-2:] == id_host.split(".")[-2:]:
        return _path_match(id_path, url_path)
    return False


def _path_match(id_path: str, url_path: str) -> bool:
    id_path = id_path.removesuffix(".git").rstrip("/").lower()
    url_path = url_path.removesuffix(".git").rstrip("/").lower()
    if not id_path:
        return False
    return url_path == id_path or url_path.endswith(f"/{id_path}")
