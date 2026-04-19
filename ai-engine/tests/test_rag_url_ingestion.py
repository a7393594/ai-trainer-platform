"""Tests for URL ingestion and HTML extraction in RAG pipeline."""
from __future__ import annotations

import pytest

from app.core.rag.pipeline import RAGPipeline


@pytest.fixture
def pipeline():
    return RAGPipeline()


def test_html_to_text_strips_tags_and_scripts(pipeline):
    html = """<html><head><title>Hello World</title></head>
<body>
  <script>alert('bad')</script>
  <style>body { color: red }</style>
  <h1>Main Heading</h1>
  <p>Some &amp; text with <a href="#">link</a></p>
</body></html>"""
    text, title = pipeline._html_to_text(html)
    assert title == "Hello World"
    assert "Main Heading" in text
    assert "Some & text" in text
    assert "alert" not in text
    assert "color: red" not in text
    assert "<" not in text and ">" not in text


def test_html_to_text_handles_missing_title(pipeline):
    text, title = pipeline._html_to_text("<html><body>Plain</body></html>")
    assert title is None
    assert text == "Plain"


@pytest.mark.asyncio
async def test_fetch_url_text_html(pipeline, monkeypatch):
    class _Resp:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        text = "<html><head><title>TT</title></head><body><p>Hi there</p></body></html>"

        def raise_for_status(self):
            pass

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            return _Resp()

    import httpx as _h
    monkeypatch.setattr(_h, "AsyncClient", _Client)

    text, title = await pipeline._fetch_url_text("https://example.com")
    assert title == "TT"
    assert "Hi there" in text


@pytest.mark.asyncio
async def test_fetch_url_text_plain(pipeline, monkeypatch):
    class _Resp:
        status_code = 200
        headers = {"content-type": "text/plain"}
        text = "Just plain text.\n\nSecond paragraph."

        def raise_for_status(self):
            pass

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            return _Resp()

    import httpx as _h
    monkeypatch.setattr(_h, "AsyncClient", _Client)

    text, title = await pipeline._fetch_url_text("https://example.com/file.txt")
    assert title is None
    assert text.startswith("Just plain text")


@pytest.mark.asyncio
async def test_upload_url_creates_doc_with_fetched_content(pipeline, monkeypatch):
    calls = {}

    async def fake_fetch(url):
        calls["url"] = url
        return "Long article content here.", "Article"

    monkeypatch.setattr(pipeline, "_fetch_url_text", fake_fetch)
    monkeypatch.setattr(
        "app.db.crud.create_knowledge_doc",
        lambda pid, title, st, content: {"id": "d1", "title": title, "source_type": st},
    )
    monkeypatch.setattr("app.db.crud.create_knowledge_chunk", lambda **kw: None)
    monkeypatch.setattr("app.db.crud.update_doc_status", lambda *a, **kw: None)

    async def fake_embed(*a, **kw):
        raise RuntimeError("skip embeddings")

    monkeypatch.setattr(pipeline, "_create_embeddings", fake_embed)

    doc = await pipeline.upload_url("p1", "https://example.com/a", title=None)
    assert doc["id"] == "d1"
    assert doc["title"] == "Article"
    assert doc["source_type"] == "url"
    assert doc["source_url"] == "https://example.com/a"
    assert doc["status"] == "ready"
    assert calls["url"] == "https://example.com/a"
