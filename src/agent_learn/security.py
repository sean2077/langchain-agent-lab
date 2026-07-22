"""Network-boundary checks for model-selected URLs."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

Resolver = Callable[..., Sequence[tuple[Any, Any, Any, Any, tuple[Any, ...]]]]
PublicDnsResolver = Callable[[str], Sequence[str]]

_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")
_PUBLIC_DNS_ENDPOINT = "https://dns.google/resolve"
_PUBLIC_DNS_ATTEMPTS_PER_RECORD = 2


class UnsafeUrlError(ValueError):
    """Raised when a URL could reach a non-public or unsupported target."""


@dataclass(frozen=True, slots=True)
class ValidatedHttpUrl:
    """A normalized logical URL and the public addresses it may connect to."""

    url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


def _require_global_address(address: str) -> None:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise UnsafeUrlError(f"invalid resolved address: {address}") from exc
    if not parsed.is_global:
        raise UnsafeUrlError(f"URL resolves to non-public address: {address}")


def _is_fake_ip_address(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return isinstance(parsed, ipaddress.IPv4Address) and parsed in _FAKE_IP_NETWORK


def _interleave_address_families(addresses: Sequence[str]) -> tuple[str, ...]:
    """Alternate families while preserving first-family and per-family order."""

    unique_addresses = tuple(dict.fromkeys(addresses))
    if not unique_addresses:
        return ()

    first_version = ipaddress.ip_address(unique_addresses[0]).version
    first_family = [
        address
        for address in unique_addresses
        if ipaddress.ip_address(address).version == first_version
    ]
    other_family = [
        address
        for address in unique_addresses
        if ipaddress.ip_address(address).version != first_version
    ]

    interleaved: list[str] = []
    for index, address in enumerate(first_family):
        interleaved.append(address)
        if index < len(other_family):
            interleaved.append(other_family[index])
    interleaved.extend(other_family[len(first_family) :])
    return tuple(interleaved)


def resolve_public_dns(hostname: str) -> tuple[str, ...]:
    """Resolve a Fake-IP hostname with DNS-over-HTTPS.

    Fake-IP DNS modes intentionally return addresses from 198.18.0.0/15, which
    cannot prove whether the origin is public. A TLS-authenticated public DNS
    answer supplies addresses that can be validated and pinned by the reader.
    """

    addresses: list[str] = []
    lookup_errors: list[Exception] = []
    with httpx.Client(timeout=5.0, follow_redirects=True, trust_env=False) as client:
        for record_type, type_number in (("A", 1), ("AAAA", 28)):
            for _attempt in range(_PUBLIC_DNS_ATTEMPTS_PER_RECORD):
                try:
                    response = client.get(
                        _PUBLIC_DNS_ENDPOINT,
                        params={"name": hostname, "type": record_type},
                        headers={"Accept": "application/dns-json"},
                    )
                    response.raise_for_status()
                    if len(response.content) > 64_000:
                        raise UnsafeUrlError("public DNS response is too large")
                    payload = response.json()
                    if payload.get("Status") == 0:
                        addresses.extend(
                            str(answer["data"])
                            for answer in payload.get("Answer", [])
                            if answer.get("type") == type_number and answer.get("data")
                        )
                    break
                except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                    lookup_errors.append(exc)

    unique_addresses = tuple(dict.fromkeys(addresses))
    if not unique_addresses and lookup_errors:
        raise UnsafeUrlError(
            f"public DNS lookup failed for hostname: {hostname}"
        ) from lookup_errors[-1]
    if not unique_addresses:
        raise UnsafeUrlError(f"hostname could not be resolved by public DNS: {hostname}")
    return unique_addresses


def validate_public_http_target(
    url: str,
    *,
    resolver: Resolver = socket.getaddrinfo,
    public_dns_resolver: PublicDnsResolver = resolve_public_dns,
) -> ValidatedHttpUrl:
    """Validate an HTTP(S) URL and return the public addresses to pin.

    Callers must repeat this validation for every redirect target. The check is a
    defense-in-depth guard for a local application, not a network sandbox.
    """

    if len(url) > 2_048:
        raise UnsafeUrlError("URL is too long")

    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"}:
        raise UnsafeUrlError("only HTTP(S) URLs are allowed")
    if not parts.hostname:
        raise UnsafeUrlError("URL must include a hostname")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrlError("credentials in URLs are not allowed")

    hostname = parts.hostname.rstrip(".").lower().encode("idna").decode("ascii")
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
        or hostname.endswith(".home.arpa")
    ):
        raise UnsafeUrlError("local hostnames are not allowed")

    try:
        explicit_port = parts.port
    except ValueError as exc:
        raise UnsafeUrlError("URL has an invalid port") from exc
    if explicit_port == 0:
        raise UnsafeUrlError("URL port must be between 1 and 65535")
    port = (
        explicit_port
        if explicit_port is not None
        else (443 if parts.scheme.lower() == "https" else 80)
    )

    try:
        literal_address = ipaddress.ip_address(hostname)
    except ValueError:
        literal_address = None

    if literal_address is not None:
        address = literal_address.compressed
        _require_global_address(address)
        addresses = (address,)
    else:
        try:
            resolved = resolver(hostname, port, 0, socket.SOCK_STREAM)
        except (OSError, socket.gaierror) as exc:
            raise UnsafeUrlError(f"hostname could not be resolved: {hostname}") from exc
        addresses = tuple(dict.fromkeys(str(item[4][0]) for item in resolved))
        if not addresses:
            raise UnsafeUrlError(f"hostname could not be resolved: {hostname}")
        if all(_is_fake_ip_address(address) for address in addresses):
            addresses = tuple(dict.fromkeys(public_dns_resolver(hostname)))
            if not addresses:
                raise UnsafeUrlError(f"hostname could not be resolved by public DNS: {hostname}")
        for address in addresses:
            _require_global_address(address)

    addresses = _interleave_address_families(addresses)

    return ValidatedHttpUrl(
        url=urlunsplit(parts),
        hostname=hostname,
        port=port,
        addresses=addresses,
    )


def validate_public_http_url(
    url: str,
    *,
    resolver: Resolver = socket.getaddrinfo,
    public_dns_resolver: PublicDnsResolver = resolve_public_dns,
) -> str:
    """Validate an HTTP(S) URL and return its normalized logical form."""

    return validate_public_http_target(
        url,
        resolver=resolver,
        public_dns_resolver=public_dns_resolver,
    ).url
