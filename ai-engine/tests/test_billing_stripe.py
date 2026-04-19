"""Tests for Stripe billing skeleton."""
from __future__ import annotations

import hmac
import hashlib

import pytest

from app.core.billing.stripe_service import StripeService, BillingError


@pytest.fixture
def svc():
    return StripeService()


@pytest.mark.asyncio
async def test_rejects_unsupported_plan(svc, monkeypatch):
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"id": "t1"})
    with pytest.raises(BillingError):
        await svc.create_checkout_session("t1", "super_elite")


@pytest.mark.asyncio
async def test_returns_mock_url_when_unconfigured(svc, monkeypatch):
    monkeypatch.setattr("app.db.crud.get_tenant", lambda _t: {"id": "t1", "settings": {}})
    monkeypatch.setattr("app.core.billing.stripe_service.settings.stripe_secret_key", "", raising=False)
    monkeypatch.setattr("app.core.billing.stripe_service.settings.stripe_price_pro", "", raising=False)
    result = await svc.create_checkout_session("t1", "pro")
    assert result["mode"] == "mock"
    assert result["configured"] is False
    assert result["url"].startswith("http")


def test_verify_signature_accepts_valid_header(svc, monkeypatch):
    monkeypatch.setattr("app.core.billing.stripe_service.settings.stripe_webhook_secret", "shh", raising=False)
    body = b'{"type":"x"}'
    expected = hmac.new(b"shh", body, hashlib.sha256).hexdigest()
    assert svc.verify_signature(body, f"t=123,v1={expected}") is True
    assert svc.verify_signature(body, expected) is True


def test_verify_signature_rejects_bad_header(svc, monkeypatch):
    monkeypatch.setattr("app.core.billing.stripe_service.settings.stripe_webhook_secret", "shh", raising=False)
    assert svc.verify_signature(b"x", "v1=deadbeef") is False
    assert svc.verify_signature(b"x", "") is False


@pytest.mark.asyncio
async def test_handle_event_applies_subscription_completed(svc, monkeypatch):
    updates_settings = {}
    updates_plan = {}
    monkeypatch.setattr(
        "app.db.crud.update_tenant_settings",
        lambda tid, p: updates_settings.update(p),
    )
    monkeypatch.setattr(
        "app.db.crud.update_tenant_plan",
        lambda tid, plan: updates_plan.update(tenant_id=tid, plan=plan),
    )
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_123",
                "subscription": "sub_123",
                "metadata": {"tenant_id": "t1", "plan": "pro"},
            }
        },
    }
    result = await svc.handle_event(event)
    assert result["status"] == "applied"
    assert result["plan"] == "pro"
    assert updates_plan == {"tenant_id": "t1", "plan": "pro"}
    assert updates_settings["stripe"]["customer_id"] == "cus_123"


@pytest.mark.asyncio
async def test_handle_event_canceled_downgrades_to_free(svc, monkeypatch):
    updated_plan = {}
    monkeypatch.setattr("app.db.crud.update_tenant_settings", lambda tid, p: None)
    monkeypatch.setattr(
        "app.db.crud.update_tenant_plan",
        lambda tid, plan: updated_plan.update(tenant_id=tid, plan=plan),
    )
    event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"metadata": {"tenant_id": "t1"}}},
    }
    result = await svc.handle_event(event)
    assert result["plan"] == "free"
    assert updated_plan["plan"] == "free"


@pytest.mark.asyncio
async def test_handle_event_without_tenant_id_ignored(svc):
    result = await svc.handle_event({"type": "checkout.session.completed", "data": {"object": {}}})
    assert result["status"] == "ignored"


@pytest.mark.asyncio
async def test_handle_event_unknown_type_ignored(svc):
    result = await svc.handle_event({
        "type": "invoice.paid",
        "data": {"object": {"metadata": {"tenant_id": "t1"}}},
    })
    assert result["status"] == "ignored"
