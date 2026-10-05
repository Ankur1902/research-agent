import hashlib
import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def detect_injection(text: str) -> bool:
    return bool(
        re.search(
            r"ignore (all |previous |your )?instructions|reveal.*(secret|environment|prompt)|send.*password|delete all users",
            text,
            re.I,
        )
    )


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
        host, address, _port = public_url(url)
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
                    from urllib.parse import urljoin

                    url = urljoin(url, response.headers["location"])
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
