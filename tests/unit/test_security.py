import socket
from collections.abc import Callable

import httpx
import pytest

from agent_learn.security import (
    UnsafeUrlError,
    resolve_public_dns,
    validate_public_http_target,
    validate_public_http_url,
)


def public_resolver(*_: object) -> list[tuple[object, object, object, object, tuple[str, int]]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class _FakeDnsResponse:
    content = b"{}"

    def __init__(self, record_type: str) -> None:
        self._record_type = record_type

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        type_number = 1 if self._record_type == "A" else 28
        address = "93.184.216.34" if type_number == 1 else "2606:2800:220:1::"
        return {
            "Status": 0,
            "Answer": [{"type": type_number, "data": address}],
        }


def _install_fake_dns_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[str], _FakeDnsResponse],
    *,
    client_kwargs: list[dict[str, object]] | None = None,
) -> None:
    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            if client_kwargs is not None:
                client_kwargs.append(kwargs)

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get(self, _url: str, **kwargs: object) -> _FakeDnsResponse:
            params = kwargs["params"]
            assert isinstance(params, dict)
            return handler(str(params["type"]))

    monkeypatch.setattr("agent_learn.security.httpx.Client", FakeClient)


def test_public_dns_resolver_does_not_inherit_proxy_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_kwargs: list[dict[str, object]] = []
    _install_fake_dns_client(
        monkeypatch,
        _FakeDnsResponse,
        client_kwargs=client_kwargs,
    )

    addresses = resolve_public_dns("example.com")

    assert addresses == ("93.184.216.34", "2606:2800:220:1::")
    assert client_kwargs == [{"timeout": 5.0, "follow_redirects": True, "trust_env": False}]


def test_public_dns_resolver_retries_transient_record_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def handler(record_type: str) -> _FakeDnsResponse:
        calls.append(record_type)
        if calls == ["A"]:
            raise httpx.ConnectTimeout("transient DoH timeout")
        return _FakeDnsResponse(record_type)

    _install_fake_dns_client(monkeypatch, handler)

    addresses = resolve_public_dns("example.com")

    assert addresses == ("93.184.216.34", "2606:2800:220:1::")
    assert calls == ["A", "A", "AAAA"]


def test_public_dns_resolver_uses_one_family_when_the_other_stays_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def handler(record_type: str) -> _FakeDnsResponse:
        calls.append(record_type)
        if record_type == "AAAA":
            raise httpx.ConnectTimeout("IPv6 DoH timeout")
        return _FakeDnsResponse(record_type)

    _install_fake_dns_client(monkeypatch, handler)

    addresses = resolve_public_dns("example.com")

    assert addresses == ("93.184.216.34",)
    assert calls == ["A", "AAAA", "AAAA"]


def test_public_dns_resolver_fails_closed_after_bounded_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def handler(record_type: str) -> _FakeDnsResponse:
        calls.append(record_type)
        raise httpx.ConnectTimeout("DoH unavailable")

    _install_fake_dns_client(monkeypatch, handler)

    with pytest.raises(UnsafeUrlError, match="public DNS lookup failed"):
        resolve_public_dns("example.com")

    assert calls == ["A", "A", "AAAA", "AAAA"]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://localhost/admin",
        "http://127.0.0.1/admin",
        "http://[::1]/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/private",
        "http://198.18.0.1/fake-ip",
        "https://user:pass@example.com/",
    ],
)
def test_validate_public_http_url_rejects_unsafe_targets(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_public_http_url(url, resolver=public_resolver)


def test_validate_public_http_url_accepts_public_https_url() -> None:
    normalized = validate_public_http_url(
        "https://example.com/research?q=agent", resolver=public_resolver
    )

    assert normalized == "https://example.com/research?q=agent"


def test_validate_public_http_target_rejects_zero_port_before_dns() -> None:
    resolver_calls: list[tuple[object, ...]] = []

    def resolver(*args: object) -> list[tuple[object, ...]]:
        resolver_calls.append(args)
        return public_resolver()

    with pytest.raises(UnsafeUrlError, match="port must be between 1 and 65535"):
        validate_public_http_target("https://example.com:0/research", resolver=resolver)

    assert resolver_calls == []


@pytest.mark.parametrize(
    ("url", "expected_port"),
    [
        ("http://example.com/research", 80),
        ("http://example.com:80/research", 80),
        ("https://example.com/research", 443),
        ("https://example.com:1/research", 1),
        ("https://example.com:443/research", 443),
        ("https://example.com:65535/research", 65535),
    ],
)
def test_validate_public_http_target_preserves_valid_port_boundaries(
    url: str,
    expected_port: int,
) -> None:
    resolved_ports: list[int] = []

    def resolver(
        _hostname: str,
        port: int,
        *_: object,
    ) -> list[tuple[object, object, object, object, tuple[str, int]]]:
        resolved_ports.append(port)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    target = validate_public_http_target(url, resolver=resolver)

    assert target.port == expected_port
    assert resolved_ports == [expected_port]


def test_validate_public_http_url_rejects_hostname_resolving_private_ip() -> None:
    def private_resolver(
        *_: object,
    ) -> list[tuple[object, object, object, object, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.12", 443))]

    with pytest.raises(UnsafeUrlError, match="non-public address"):
        validate_public_http_url("https://example.com", resolver=private_resolver)


def test_validate_public_http_target_resolves_fake_ip_through_public_dns() -> None:
    def fake_ip_resolver(
        *_: object,
    ) -> list[tuple[object, object, object, object, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.42", 443))]

    target = validate_public_http_target(
        "https://example.com/research",
        resolver=fake_ip_resolver,
        public_dns_resolver=lambda _hostname: ["93.184.216.34"],
    )

    assert target.url == "https://example.com/research"
    assert target.hostname == "example.com"
    assert target.port == 443
    assert target.addresses == ("93.184.216.34",)


def test_validate_public_http_target_rejects_private_public_dns_answer() -> None:
    def fake_ip_resolver(
        *_: object,
    ) -> list[tuple[object, object, object, object, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.42", 443))]

    with pytest.raises(UnsafeUrlError, match="non-public address"):
        validate_public_http_target(
            "https://example.com/research",
            resolver=fake_ip_resolver,
            public_dns_resolver=lambda _hostname: ["192.168.1.12"],
        )


@pytest.mark.parametrize(
    ("addresses", "expected"),
    [
        (
            (
                "2606:4700:4700::1111",
                "2001:4860:4860::8888",
                "1.1.1.1",
                "8.8.8.8",
                "2620:fe::fe",
            ),
            (
                "2606:4700:4700::1111",
                "1.1.1.1",
                "2001:4860:4860::8888",
                "8.8.8.8",
                "2620:fe::fe",
            ),
        ),
        (
            (
                "1.1.1.1",
                "8.8.8.8",
                "2606:4700:4700::1111",
                "2001:4860:4860::8888",
                "9.9.9.9",
            ),
            (
                "1.1.1.1",
                "2606:4700:4700::1111",
                "8.8.8.8",
                "2001:4860:4860::8888",
                "9.9.9.9",
            ),
        ),
        (
            ("1.1.1.1", "8.8.8.8", "1.1.1.1", "9.9.9.9"),
            ("1.1.1.1", "8.8.8.8", "9.9.9.9"),
        ),
    ],
)
def test_validate_public_http_target_stably_interleaves_address_families(
    addresses: tuple[str, ...],
    expected: tuple[str, ...],
) -> None:
    def resolver(
        *_: object,
    ) -> list[tuple[object, object, object, object, tuple[object, ...]]]:
        return [
            (
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (address, 443, 0, 0) if ":" in address else (address, 443),
            )
            for address in addresses
        ]

    target = validate_public_http_target("https://example.com/research", resolver=resolver)

    assert target.addresses == expected


def test_validate_public_http_target_interleaves_public_dns_families() -> None:
    def fake_ip_resolver(
        *_: object,
    ) -> list[tuple[object, object, object, object, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.42", 443))]

    target = validate_public_http_target(
        "https://example.com/research",
        resolver=fake_ip_resolver,
        public_dns_resolver=lambda _hostname: [
            "1.1.1.1",
            "8.8.8.8",
            "2606:4700:4700::1111",
            "2001:4860:4860::8888",
        ],
    )

    assert target.addresses == (
        "1.1.1.1",
        "2606:4700:4700::1111",
        "8.8.8.8",
        "2001:4860:4860::8888",
    )


def test_validate_public_http_target_preserves_public_ip_literal() -> None:
    target = validate_public_http_target("https://[2606:4700:4700::1111]/research")

    assert target.hostname == "2606:4700:4700::1111"
    assert target.addresses == ("2606:4700:4700::1111",)
