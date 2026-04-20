"""
Tenant SSO / OAuth — 企業登入設定

底層仍倚靠 Supabase Auth 提供的 OAuth providers（Google、Azure AD、SAML、GitHub…），
這層負責：

  1) per-tenant 設定：
       - allowed_email_domains   : ["acme.com", "acme.co.jp"]
       - oauth_providers         : ["google", "azure", "saml"]
       - enforced                : bool — true 時要求必須用 SSO 登入
       - sso_entity_id           : str (SAML 用)
       - sso_metadata_url        : str (SAML 用)
     儲存於 tenants.settings.sso

  2) 解析：email → tenant（`resolve_tenant_by_email(email)`），讓登入頁知道
     把使用者導向哪個 IdP

  3) enforce_login_allowed(email): 拒絕來路不明的 email 若租戶啟用了白名單
"""
from __future__ import annotations

from typing import Optional

from app.db import crud
from app.db.supabase import get_supabase


class SSOError(Exception):
    pass


class SSOService:

    def get_config(self, tenant_id: str) -> dict:
        tenant = crud.get_tenant(tenant_id) or {}
        settings = tenant.get("settings") or {}
        sso = dict(settings.get("sso") or {})
        sso.setdefault("allowed_email_domains", [])
        sso.setdefault("oauth_providers", [])
        sso.setdefault("enforced", False)
        sso.setdefault("sso_entity_id", "")
        sso.setdefault("sso_metadata_url", "")
        return {"tenant_id": tenant_id, **sso}

    def update_config(
        self,
        tenant_id: str,
        *,
        allowed_email_domains: Optional[list[str]] = None,
        oauth_providers: Optional[list[str]] = None,
        enforced: Optional[bool] = None,
        sso_entity_id: Optional[str] = None,
        sso_metadata_url: Optional[str] = None,
    ) -> Optional[dict]:
        patch: dict = {}
        if allowed_email_domains is not None:
            patch["allowed_email_domains"] = [d.strip().lower() for d in allowed_email_domains if d and d.strip()]
        if oauth_providers is not None:
            allowed = {"google", "azure", "github", "gitlab", "apple", "saml", "okta"}
            patch["oauth_providers"] = [p for p in (oauth_providers or []) if p in allowed]
        if enforced is not None:
            patch["enforced"] = bool(enforced)
        if sso_entity_id is not None:
            patch["sso_entity_id"] = str(sso_entity_id)
        if sso_metadata_url is not None:
            patch["sso_metadata_url"] = str(sso_metadata_url)
        if not patch:
            return None
        # Merge into tenants.settings.sso without clobbering other settings
        tenant = crud.get_tenant(tenant_id)
        if not tenant:
            return None
        existing = (tenant.get("settings") or {}).get("sso") or {}
        merged_sso = {**existing, **patch}
        return crud.update_tenant_settings(tenant_id, {"sso": merged_sso})

    def resolve_tenant_by_email(self, email: str) -> Optional[dict]:
        """Lookup which tenant (if any) owns this email domain.

        Returns a hint so the login UI can pre-select the right IdP:
          {tenant_id, domain, oauth_providers, enforced}
        """
        if not email or "@" not in email:
            return None
        domain = email.rsplit("@", 1)[-1].strip().lower()
        if not domain:
            return None
        db = get_supabase()
        tenants = (
            db.table("ait_tenants").select("id,settings").execute().data or []
        )
        for t in tenants:
            sso = ((t.get("settings") or {}).get("sso") or {})
            domains = [d.lower() for d in (sso.get("allowed_email_domains") or [])]
            if domain in domains:
                return {
                    "tenant_id": t["id"],
                    "domain": domain,
                    "oauth_providers": sso.get("oauth_providers") or [],
                    "enforced": bool(sso.get("enforced", False)),
                    "sso_entity_id": sso.get("sso_entity_id") or None,
                }
        return None

    def enforce_login_allowed(self, email: str) -> None:
        """Raise SSOError if any tenant has enforced SSO for this domain but the
        current flow uses email/password (caller is expected to pass in a flag
        indicating OAuth vs password).

        Here we keep the check simple: any enforced tenant covering the domain
        blocks non-OAuth logins. The auth layer decides what to do with the
        exception (render a 403 with the IdP hint).
        """
        resolved = self.resolve_tenant_by_email(email)
        if resolved and resolved["enforced"]:
            raise SSOError(
                f"SSO enforced for domain {resolved['domain']}; please log in via "
                f"{', '.join(resolved['oauth_providers']) or 'the configured provider'}"
            )


sso_service = SSOService()
