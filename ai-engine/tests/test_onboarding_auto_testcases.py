"""Tests for Onboarding auto-generated test cases."""
from __future__ import annotations

import pytest

from app.core.orchestrator.onboarding import OnboardingManager


class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


@pytest.mark.asyncio
async def test_generate_test_cases_parses_json_and_saves(monkeypatch):
    manager = OnboardingManager()

    async def fake_chat(**_kw):
        return _FakeResp(
            '[{"input":"Q1","expected":"E1","category":"c1"},'
            ' {"input":"Q2","expected":"E2","category":"c2"}]'
        )

    monkeypatch.setattr("app.core.orchestrator.onboarding.chat_completion", fake_chat)

    saved = []
    monkeypatch.setattr(
        "app.db.crud.create_test_case",
        lambda pid, inp, exp, cat: saved.append((pid, inp, exp, cat)),
    )

    n = await manager._generate_test_cases("p1", "system-prompt", "qa-summary", count=2)
    assert n == 2
    assert saved[0][0] == "p1"
    assert saved[0][1] == "Q1"


@pytest.mark.asyncio
async def test_generate_test_cases_handles_malformed(monkeypatch):
    manager = OnboardingManager()

    async def fake_chat(**_kw):
        return _FakeResp("nothing-json-here")

    monkeypatch.setattr("app.core.orchestrator.onboarding.chat_completion", fake_chat)

    n = await manager._generate_test_cases("p", "sp", "qa", count=5)
    assert n == 0


@pytest.mark.asyncio
async def test_generate_test_cases_skips_empty_fields(monkeypatch):
    manager = OnboardingManager()

    async def fake_chat(**_kw):
        return _FakeResp('[{"input":"","expected":"x"},{"input":"q","expected":""}]')

    monkeypatch.setattr("app.core.orchestrator.onboarding.chat_completion", fake_chat)
    saved = []
    monkeypatch.setattr("app.db.crud.create_test_case", lambda *a: saved.append(a))

    n = await manager._generate_test_cases("p", "sp", "qa", count=2)
    assert n == 0
    assert saved == []
