"""Tests for Tenant SSO service."""
from __future__ import annotations

import pytest

from app.core.sso.service import SSOService, SSOError


@pytest.fixture
def svc():
    return SSOService()


def test_get_config_defaults(monkeypatch, svc):
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"id": "t1", "settings": {}})
    cfg = svc.get_config("t1")
    assert cfg["allowed_email_domains"] == []
    assert cfg["oauth_providers"] == []
    assert cfg["enforced"] is False


def test_update_config_normalizes_domains_and_providers(monkeypatch, svc):
    stored = {}
    monkeypatch.setattr(
        "app.db.crud.get_tenant",
        lambda _t: {"id": "t1", "settings": {"sso": {"allowed_email_domains": ["old.com"]}}},
    )
    monkeypatch.setattr(
        "app.db.crud.update_tenant_settings",
        lambda tid, p: stored.update(p) or {"id": tid, "settings": p},
    )
    svc.update_config(
        "t1",
        allowed_email_domains=["ACME.com", " example.org "],
        oauth_providers=["google", "nonsense", "saml"],
        enforced=True,
    )
    assert stored["sso"]["allowed_email_domains"] == ["acme.com", "example.org"]
    assert stored["sso"]["oauth_providers"] == ["google", "saml"]
    assert stored["sso"]["enforced"] is True


def test_update_config_merges_with_existing(monkeypatch, svc):
    stored = {}
    monkeypatch.setattr(
        "app.db.crud.get_tenant",
        lambda _t: {"id": "t1", "settings": {"sso": {"oauth_providers": ["google"], "enforced": False}}},
    )
    monkeypatch.setattr(
        "app.db.crud.update_tenant_settings",
        lambda tid, p: stored.update(p) or {"id": tid},
    )
    svc.update_config("t1", allowed_email_domains=["acme.com"])
    # Existing providers should survive
    assert stored["sso"]["oauth_providers"] == ["google"]
    assert stored["sso"]["allowed_email_domains"] == ["acme.com"]


def test_resolve_tenant_by_email_matches_domain(monkeypatch, svc):
    tenants = [
        {"id": "t1", "settings": {"sso": {"allowed_email_domains": ["acme.com"], "oauth_providers": ["google"]}}},
        {"id": "t2", "settings": {"sso": {"allowed_email_domains": ["widget.co"]}}},
    ]

    class _Chain:
        def __init__(self, data):
            self._d = data
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def execute(self):
            return type("R", (), {"data": self._d})()

    class _Client:
        def table(self, _name):
            return _Chain(tenants)

    monkeypatch.setattr("app.core.sso.service.get_supabase", lambda: _Client())
    hint = svc.resolve_tenant_by_email("alice@acme.com")
    assert hint["tenant_id"] == "t1"
    assert hint["oauth_providers"] == ["google"]


def test_resolve_tenant_by_email_no_match(monkeypatch, svc):
    class _Chain:
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def execute(self):
            return type("R", (), {"data": []})()

    class _Client:
        def table(self, _name):
            return _Chain()

    monkeypatch.setattr("app.core.sso.service.get_supabase", lambda: _Client())
    assert svc.resolve_tenant_by_email("u@nothing.com") is None


def test_resolve_rejects_invalid_email(svc):
    assert svc.resolve_tenant_by_email("no-at-sign") is None
    assert svc.resolve_tenant_by_email("") is None


def test_enforce_login_allowed_raises_when_enforced(monkeypatch, svc):
    tenants = [{"id": "t1", "settings": {"sso": {"allowed_email_domains": ["acme.com"], "enforced": True, "oauth_providers": ["google"]}}}]

    class _Chain:
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def execute(self):
            return type("R", (), {"data": tenants})()

    class _Client:
        def table(self, _name):
            return _Chain()

    monkeypatch.setattr("app.core.sso.service.get_supabase", lambda: _Client())
    with pytest.raises(SSOError):
        svc.enforce_login_allowed("bob@acme.com")


def test_enforce_login_allowed_passes_when_not_enforced(monkeypatch, svc):
    tenants = [{"id": "t1", "settings": {"sso": {"allowed_email_domains": ["acme.com"], "enforced": False}}}]

    class _Chain:
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def execute(self):
            return type("R", (), {"data": tenants})()

    class _Client:
        def table(self, _name):
            return _Chain()

    monkeypatch.setattr("app.core.sso.service.get_supabase", lambda: _Client())
    # Should not raise
    svc.enforce_login_allowed("bob@acme.com")
