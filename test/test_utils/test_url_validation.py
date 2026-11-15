from __future__ import annotations

import pytest

from pybreeze.utils.network.url_validation import UnsafeURLError, validate_url


class TestSchemeValidation:
    @pytest.mark.parametrize("url", [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com/",
        "data:text/plain;base64,AAAA",
    ])
    def test_non_http_schemes_rejected(self, url):
        with pytest.raises(UnsafeURLError):
            validate_url(url)

    def test_missing_hostname_rejected(self):
        with pytest.raises(UnsafeURLError):
            validate_url("http:///nohost")


class TestPrivateAddressBlocking:
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/",          # loopback
        "http://10.0.0.1/",           # RFC1918
        "http://192.168.1.1/",        # RFC1918
        "http://172.16.0.1/",         # RFC1918
        "http://169.254.169.254/",    # link-local / cloud metadata
        "http://0.0.0.0/",            # unspecified
        "http://100.64.0.1/",         # RFC6598 CGNAT
        "http://224.0.0.1/",          # multicast
        "http://[::1]/",              # IPv6 loopback
        "http://[fe80::1]/",          # IPv6 link-local
        "http://[fec0::1]/",          # IPv6 site-local (deprecated, still routed in places)
        "http://[4000::1]/",          # IPv6 reserved: neither private nor non-global to Python, only reserved
        "http://240.0.0.1/",          # IPv4 reserved (class E)
    ])
    def test_blocked(self, url):
        with pytest.raises(UnsafeURLError):
            validate_url(url)


class TestIPv6TransitionForms:
    """IPv6 wrappers that route to the blocked cloud-metadata IPv4 (169.254.169.254)."""

    @pytest.mark.parametrize("url", [
        "http://[::ffff:169.254.169.254]/",   # IPv4-mapped
        "http://[2002:a9fe:a9fe::1]/",         # 6to4 wrapping 169.254.169.254
        "http://[64:ff9b::a9fe:a9fe]/",        # NAT64 well-known prefix
    ])
    def test_transition_form_to_metadata_blocked(self, url):
        with pytest.raises(UnsafeURLError):
            validate_url(url)


class TestPublicAddressAllowed:
    @pytest.mark.parametrize("url", [
        "http://8.8.8.8/",
        "https://1.1.1.1/path?q=1",
        "http://[2606:4700:4700::1111]/",  # Cloudflare public IPv6
    ])
    def test_public_ip_allowed(self, url):
        assert validate_url(url) == url


class TestHostnamesThatCannotBeLookedUp:
    """Whatever a hostname is, the answer is an UnsafeURLError, not a stray exception.

    A caller catches ``UnsafeURLError``; anything else escapes its handler and,
    in a Qt slot, takes the application with it.
    """

    @pytest.mark.parametrize("url", [
        "http://" + "a" * 70 + ".example",
        "http://.example",
        "http://exa mple.example",
        "http://" + "b" * 300,
    ], ids=["label too long", "empty label", "space in hostname", "name too long"])
    def test_an_impossible_hostname_is_refused_like_any_other(self, url):
        with pytest.raises(UnsafeURLError):
            validate_url(url)


class TestTheAddressesOfAName:
    @staticmethod
    def _resolving(monkeypatch, *addresses):
        import socket

        from pybreeze.utils.network import url_validation

        answer = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0)) for address in addresses]
        monkeypatch.setattr(url_validation.socket, "getaddrinfo", lambda *_a, **_k: answer)

    def test_a_name_with_no_address_is_refused(self, monkeypatch):
        from pybreeze.utils.network.url_validation import public_addresses

        self._resolving(monkeypatch)
        with pytest.raises(UnsafeURLError, match="Cannot resolve hostname 'example.com'"):
            public_addresses("example.com")

    def test_each_address_comes_once_in_the_resolvers_order(self, monkeypatch):
        # The resolver repeats an address once per socket type it was not asked to filter
        from pybreeze.utils.network.url_validation import public_addresses

        self._resolving(monkeypatch, "93.184.215.14", "93.184.215.14", "8.8.8.8", "93.184.215.14")
        assert public_addresses("example.com") == ["93.184.215.14", "8.8.8.8"]


class TestTheIPv4InsideAnIPv6Wrapper:
    """The standard library already refuses Teredo (private) and NAT64 (reserved) addresses.

    ``_embedded_ipv4`` is the check behind that, should a Python version class
    them otherwise, as 3.12 and 3.13 reclassified other ranges: it must find
    the IPv4 each wrapper routes to, and the suite never reached it.
    """

    @pytest.mark.parametrize(("wrapped", "inside"), [
        ("::ffff:169.254.169.254", "169.254.169.254"),                  # IPv4-mapped
        ("2002:a9fe:a9fe::1", "169.254.169.254"),                       # 6to4
        ("2001:0:0:0:0:0:5601:5601", "169.254.169.254"),                # Teredo: the client, inverted
        ("64:ff9b::a9fe:a9fe", "169.254.169.254"),                      # NAT64 well-known prefix
    ])
    def test_the_address_it_routes_to_is_found(self, wrapped, inside):
        import ipaddress

        from pybreeze.utils.network.url_validation import _embedded_ipv4

        assert ipaddress.ip_address(inside) in _embedded_ipv4(ipaddress.ip_address(wrapped))

    def test_a_plain_ipv6_address_wraps_nothing(self):
        import ipaddress

        from pybreeze.utils.network.url_validation import _embedded_ipv4

        assert _embedded_ipv4(ipaddress.ip_address("2606:4700:4700::1111")) == []


class TestLocalAddressesTheUserMayAllow:
    """A local model server: refused, unless the user was shown its address and said yes."""

    @staticmethod
    def _resolving(monkeypatch, *addresses):
        import socket

        from pybreeze.utils.network import url_validation

        answer = [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))
            for address in addresses]
        monkeypatch.setattr(url_validation.socket, "getaddrinfo", lambda *_a, **_k: answer)

    @pytest.mark.parametrize("address", ["127.0.0.1", "::1", "10.0.0.5", "172.16.3.3", "192.168.1.9", "fd00::1"])
    def test_a_loopback_or_private_address_is_refused_as_one_that_may_be_allowed(self, monkeypatch, address):
        from pybreeze.utils.network.url_validation import LocalAddressNeedsApprovalError

        self._resolving(monkeypatch, address)

        with pytest.raises(LocalAddressNeedsApprovalError) as refused:
            validate_url("http://model.test:11434/api")

        assert refused.value.host == "model.test"
        assert refused.value.addresses == (address,)

    def test_it_is_still_the_refusal_every_other_caller_expects(self, monkeypatch):
        self._resolving(monkeypatch, "127.0.0.1")

        with pytest.raises(UnsafeURLError, match="127.0.0.1"):
            validate_url("http://model.test/")

    @pytest.mark.parametrize("address", [
        "169.254.169.254", "100.64.0.1", "0.0.0.0", "224.0.0.1", "240.0.0.1", "255.255.255.255",
        "::", "fe80::1", "fec0::1", "ff02::1", "::ffff:127.0.0.1", "::ffff:10.0.0.5",
        "64:ff9b::7f00:1", "2002:7f00:1::", "2001:0:4136:e378:8000:63bf:3fff:fdd2"])
    def test_what_may_never_be_allowed_is_refused_outright(self, monkeypatch, address):
        from pybreeze.utils.network.url_validation import LocalAddressNeedsApprovalError

        self._resolving(monkeypatch, address)

        with pytest.raises(UnsafeURLError) as refused:
            validate_url("http://model.test/")

        assert not isinstance(refused.value, LocalAddressNeedsApprovalError)

    @pytest.mark.parametrize("address", ["169.254.169.254", "100.64.0.1", "::ffff:127.0.0.1", "0.0.0.0"])
    def test_allowing_one_changes_nothing(self, monkeypatch, address):
        # A caller cannot widen what may be allowed by passing the address back
        self._resolving(monkeypatch, address)

        with pytest.raises(UnsafeURLError):
            validate_url("http://model.test/", allowed_local=[address])

    def test_an_allowed_address_passes(self, monkeypatch):
        from pybreeze.utils.network.url_validation import public_addresses

        self._resolving(monkeypatch, "127.0.0.1")

        assert validate_url("http://model.test/", allowed_local={"127.0.0.1"}) == "http://model.test/"
        assert public_addresses("model.test", {"127.0.0.1"}) == ["127.0.0.1"]

    def test_an_allowed_address_is_the_same_however_it_is_written(self, monkeypatch):
        from pybreeze.utils.network.url_validation import public_addresses

        self._resolving(monkeypatch, "::1")

        assert public_addresses("model.test", ["0:0:0:0:0:0:0:1", "not an address"]) == ["::1"]

    def test_only_the_address_allowed_passes(self, monkeypatch):
        # Asked about 127.0.0.1, the name then answers another private address
        from pybreeze.utils.network.url_validation import LocalAddressNeedsApprovalError

        self._resolving(monkeypatch, "10.0.0.5")

        with pytest.raises(LocalAddressNeedsApprovalError) as refused:
            validate_url("http://model.test/", allowed_local={"127.0.0.1"})

        assert refused.value.addresses == ("10.0.0.5",)

    def test_every_address_of_the_name_has_to_be_allowed(self, monkeypatch):
        from pybreeze.utils.network.url_validation import LocalAddressNeedsApprovalError

        self._resolving(monkeypatch, "127.0.0.1", "192.168.1.9", "192.168.1.9")

        with pytest.raises(LocalAddressNeedsApprovalError) as refused:
            validate_url("http://model.test/", allowed_local={"127.0.0.1"})

        assert refused.value.addresses == ("192.168.1.9",)

    def test_one_address_that_may_not_be_allowed_refuses_the_name_outright(self, monkeypatch):
        from pybreeze.utils.network.url_validation import LocalAddressNeedsApprovalError

        self._resolving(monkeypatch, "127.0.0.1", "169.254.169.254")

        with pytest.raises(UnsafeURLError) as refused:
            validate_url("http://model.test/")

        assert not isinstance(refused.value, LocalAddressNeedsApprovalError)

    def test_a_public_name_with_a_local_address_beside_it_names_only_the_local_one(self, monkeypatch):
        from pybreeze.utils.network.url_validation import LocalAddressNeedsApprovalError

        self._resolving(monkeypatch, "93.184.215.14", "127.0.0.1")

        with pytest.raises(LocalAddressNeedsApprovalError) as refused:
            validate_url("http://model.test/")

        assert refused.value.addresses == ("127.0.0.1",)

    def test_a_literal_address_is_asked_about_under_itself(self):
        from pybreeze.utils.network.url_validation import LocalAddressNeedsApprovalError

        with pytest.raises(LocalAddressNeedsApprovalError) as refused:
            validate_url("http://127.0.0.1:11434/api")

        assert (refused.value.host, refused.value.addresses) == ("127.0.0.1", ("127.0.0.1",))

    def test_allowing_does_not_open_another_scheme(self):
        with pytest.raises(UnsafeURLError):
            validate_url("file://127.0.0.1/etc/passwd", allowed_local={"127.0.0.1"})
