"""
Stripe Checkout Skeleton — 方案升級流程

設計：
  - 支援 pro / enterprise 兩個方案（對應 stripe_price_pro / stripe_price_enterprise）
  - stripe_customer_id / stripe_subscription_id 儲存在 tenants.settings.stripe
  - create_checkout_session() 回傳 Stripe Checkout URL（無 stripe SDK 時回 mock URL）
  - handle_webhook() 接 checkout.session.completed / customer.subscription.updated|deleted，
    同步 tenants.plan 欄位

最小可用：無 stripe_secret_key 時仍可回 mock URL，前端顯示「尚未配置 Stripe」提示。
"""
from __future__ import annotations

import hmac
import hashlib
import time
from typing import Any, Optional

from app.config import settings
from app.db import crud


class BillingError(Exception):
    pass


def _price_id(plan: str) -> Optional[str]:
    if plan == "pro":
        return settings.stripe_price_pro
    if plan == "enterprise":
        return settings.stripe_price_enterprise
    return None


class StripeService:

    def configured(self) -> bool:
        return bool(settings.stripe_secret_key)

    async def create_checkout_session(
        self,
        tenant_id: str,
        plan: str,
        user_email: Optional[str] = None,
    ) -> dict:
        if plan not in ("pro", "enterprise"):
            raise BillingError(f"Unsupported plan: {plan}")
        tenant = crud.get_tenant(tenant_id)
        if not tenant:
            raise BillingError("Tenant not found")

        price = _price_id(plan)

        if not self.configured() or not price:
            # 沒配置 Stripe → 回 mock 以便 UI 可測
            mock_id = f"cs_mock_{int(time.time())}"
            return {
                "mode": "mock",
                "url": f"{settings.billing_success_url}?mock=1&session_id={mock_id}",
                "session_id": mock_id,
                "plan": plan,
                "price_id": None,
                "configured": False,
            }

        try:
            import stripe  # lazy import
        except ImportError:
            raise BillingError("stripe package not installed")

        stripe.api_key = settings.stripe_secret_key
        existing_settings = (tenant.get("settings") or {})
        stripe_meta = existing_settings.get("stripe") or {}

        checkout_kwargs: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price, "quantity": 1}],
            "success_url": f"{settings.billing_success_url}?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": settings.billing_cancel_url,
            "metadata": {"tenant_id": tenant_id, "plan": plan},
            "subscription_data": {"metadata": {"tenant_id": tenant_id, "plan": plan}},
        }
        if stripe_meta.get("customer_id"):
            checkout_kwargs["customer"] = stripe_meta["customer_id"]
        elif user_email:
            checkout_kwargs["customer_email"] = user_email

        session = stripe.checkout.Session.create(**checkout_kwargs)
        return {
            "mode": "live",
            "url": session.url,
            "session_id": session.id,
            "plan": plan,
            "price_id": price,
            "configured": True,
        }

    def verify_signature(self, payload: bytes, signature_header: str) -> bool:
        """Simple HMAC-SHA256 check against stripe_webhook_secret.

        Stripe's real verification uses timestamp + tolerance; this is a
        pragmatic simplification for the skeleton. Prod deployments should
        use stripe.Webhook.construct_event instead.
        """
        secret = (settings.stripe_webhook_secret or "").encode()
        if not secret or not signature_header:
            return False
        expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        # Stripe sig format is `t=...,v1=<hex>`; accept either raw hex or full header
        if "v1=" in signature_header:
            provided = signature_header.split("v1=")[-1].split(",")[0]
        else:
            provided = signature_header
        return hmac.compare_digest(expected, provided)

    async def handle_event(self, event: dict) -> dict:
        """Apply subscription events to tenants.plan + tenants.settings.stripe."""
        event_type = event.get("type", "")
        data = (event.get("data") or {}).get("object", {}) or {}
        metadata = data.get("metadata") or {}
        tenant_id = metadata.get("tenant_id") or (data.get("subscription_details") or {}).get("metadata", {}).get("tenant_id")

        if not tenant_id:
            return {"status": "ignored", "reason": "no tenant_id in metadata"}

        patch: dict = {}
        new_plan: Optional[str] = None

        if event_type == "checkout.session.completed":
            new_plan = metadata.get("plan")
            patch["stripe"] = {
                "customer_id": data.get("customer"),
                "subscription_id": data.get("subscription"),
                "plan": new_plan,
                "activated_at": time.time(),
            }
        elif event_type == "customer.subscription.updated":
            status = data.get("status")
            patch["stripe"] = {
                "customer_id": data.get("customer"),
                "subscription_id": data.get("id"),
                "status": status,
                "plan": metadata.get("plan"),
                "updated_at": time.time(),
            }
            if status in ("active", "trialing"):
                new_plan = metadata.get("plan")
            elif status in ("canceled", "unpaid", "past_due"):
                new_plan = "free"
        elif event_type == "customer.subscription.deleted":
            patch["stripe"] = {"canceled_at": time.time()}
            new_plan = "free"
        else:
            return {"status": "ignored", "reason": f"unhandled event {event_type}"}

        crud.update_tenant_settings(tenant_id, patch)
        if new_plan:
            crud.update_tenant_plan(tenant_id, new_plan)
        return {"status": "applied", "tenant_id": tenant_id, "plan": new_plan, "event": event_type}


stripe_service = StripeService()
