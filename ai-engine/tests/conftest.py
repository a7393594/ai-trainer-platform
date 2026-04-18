"""Pytest fixtures shared across the test suite.

Tests run without real Supabase/LLM credentials. We inject minimal env vars so
`app.config.Settings` loads, and stub modules that talk to external services.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

# Ensure ai-engine root is on sys.path so `import app...` works
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Minimum env vars required by pydantic Settings
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-key")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("ENVIRONMENT", "test")


# ---------------------------------------------------------------------------
# Stub heavy external deps so tests don't need real packages installed.
# These modules are only used at import time by files we exercise; real calls
# are monkeypatched per-test.
# ---------------------------------------------------------------------------
def _install_stub(name: str, attrs: dict | None = None) -> None:
    if name in sys.modules:
        return
    mod = types.ModuleType(name)
    for k, v in (attrs or {}).items():
        setattr(mod, k, v)
    sys.modules[name] = mod


# supabase — used by app.db.supabase
class _StubClient:
    def table(self, *_a, **_kw):
        raise RuntimeError("supabase stub: real DB access not available in tests")


_install_stub("supabase", {
    "create_client": lambda *a, **kw: _StubClient(),
    "Client": _StubClient,
})

# litellm / langfuse / openai / anthropic / cryptography are imported lazily
# inside code paths we patch; stubs provide import-safety only.
_install_stub("litellm")
_install_stub("langfuse")
_install_stub("langfuse.client", {"Langfuse": object})
_install_stub("cryptography")
_install_stub("cryptography.fernet", {"Fernet": type("Fernet", (), {"__init__": lambda self, *a, **kw: None})})
_install_stub("openai")
_install_stub("anthropic")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fake_supabase(monkeypatch):
    """Patch `app.db.supabase.get_supabase` with an in-memory stub."""

    class _Chain:
        def __init__(self, rows):
            self._rows = rows
            self.data = rows

        def eq(self, *_args, **_kw):
            return self
        neq = eq
        gt = eq
        gte = eq
        lt = eq
        lte = eq
        like = eq
        ilike = eq
        in_ = eq

        def select(self, *_args, **_kw):
            return self

        def order(self, *_args, **_kw):
            return self

        def limit(self, *_args, **_kw):
            return self

        def insert(self, payload):
            self.data = [payload] if isinstance(payload, dict) else payload
            return self

        def update(self, payload):
            self.data = [payload]
            return self

        def execute(self):
            return types.SimpleNamespace(data=self.data)

    class _Client:
        def __init__(self):
            self._tables: dict[str, list] = {}

        def table(self, name):
            return _Chain(self._tables.setdefault(name, []))

    client = _Client()
    monkeypatch.setattr("app.db.supabase.get_supabase", lambda: client)
    return client
