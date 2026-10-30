import asyncio
import hashlib
import ipaddress
import re
import socket
import unicodedata
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


_INJECTION = re.compile(
    r"(ignore|disregard|forget|override)\W+(all\W+|any\W+|the\W+|previous\W+|prior\W+|above\W+|your\W+)*"
    r"(instructions|rules|guidelines|prompts?)"
    r"|reveal.{0,40}(secret|environment|system prompt|credential|api key)"
    r"|(send|post|exfiltrate).{0,40}(password|credential|token|api key)"
    r"|delete all users",
    re.I | re.S,
)
_INVISIBLE = dict.fromkeys([0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD])


def detect_injection(text: str) -> bool:
    """Heuristic only: NFKC and zero-width stripping defeat trivial obfuscation, not a determined attacker."""
    return bool(_INJECTION.search(unicodedata.normalize("NFKC", text).translate(_INVISIBLE)))


_SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\btvly-[A-Za-z0-9_-]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def redact_secrets(value):
    """Recursively replace credential-shaped strings in model output before it is persisted."""
    if isinstance(value, str):
        for pattern in _SECRET_PATTERNS:
            value = pattern.sub("[REDACTED]", value)
        return value
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_secrets(item) for key, item in value.items()}
    return value


async def throttle(redis, key: str, limit: int, window: int = 60) -> bool:
    """Fixed-window counter; True when the caller is still within the limit."""
    bucket = f"rate:{key}"
    count = await redis.incr(bucket)
    if count == 1:
        await redis.expire(bucket, window)
    return count <= limit


def public_url(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Unsafe source URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in {80, 443}:
        raise ValueError("Nonstandard source port")
    addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Source resolves to an internal or reserved address")
    return parsed.hostname, str(addresses[0][4][0]), port


async def fetch_public(url: str) -> str:
    # Connect to the validated IP, retaining the hostname for TLS and Host.
    # No proxy environment is trusted and each redirect is checked separately.
    for _ in range(4):
        host, address, _port = await asyncio.to_thread(public_url, url)  # DNS must not block the event loop
        parsed = urlparse(url)
        netloc = f"[{address}]" if ":" in address else address
        pinned = parsed._replace(netloc=netloc).geturl()
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
            async with client.stream(
                "GET",
                pinned,
                headers={"Host": host, "User-Agent": "ResearchOS/1.0"},
                extensions={"sni_hostname": host},
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Redirect without a destination")
                    url = urljoin(url, location)
                    continue
                response.raise_for_status()
                if "text/" not in response.headers.get("content-type", ""):
                    raise ValueError("Web research accepts text pages only")
                data = bytearray()
                async for part in response.aiter_bytes():
                    data.extend(part)
                    if len(data) > 2_000_000:
                        raise ValueError("Source exceeds download limit")
                return data.decode("utf-8", errors="replace")
    raise ValueError("Too many redirects")


def require_role(role: str, allowed: set[str]):
    if role not in allowed:
        raise HTTPException(403, "Insufficient organization role")


def validate_readonly_sql(sql: str):
    # Deliberately narrow: registry offers predeclared tenant-scoped queries only.
    if not re.fullmatch(r"SELECT (COUNT\(\*\)|id, name) FROM (projects|documents)", sql, re.I):
        raise ValueError("Only predefined read-only queries are permitted")
