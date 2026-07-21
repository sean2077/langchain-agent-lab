import socket

import pytest

from agent_learn.security import (
    UnsafeUrlError,
    validate_public_http_target,
    validate_public_http_url,
)


def public_resolver(*_: object) -> list[tuple[object, object, object, object, tuple[str, int]]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


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
