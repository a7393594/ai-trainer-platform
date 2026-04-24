"""Generic LLM call primitive — replaces analyze_intent / triage_llm / parse_widget /
compose_prompt and the legacy `call_model` node's planner-and-execute combo.

One node, three modes via `output_format`:
  - "text"        : plain text response (default)
  - "json"        : enforce JSON output, with optional `output_schema` and
                    auto-retry on parse failure
  - "tool_calls"  : model can produce tool calls; if `auto_execute_tools` is
                    True we loop tool exec → feedback → next call until done
                    or `max_iterations` hit

The user_prompt_template is rendered with `{{node.field}}` substitution before
being sent. system_prompt is sent as-is (use prompt library refs for that).

Output dict (written to `ctx.node_outputs[node_id]`):
  {
    "text": str,           # always present, the final assistant text
    "json": dict | None,   # populated when output_format=json and parse OK
    "tool_calls": [...],   # populated when output_format=tool_calls
    "tool_results": [...], # auto_execute mode loop results
    "model": str,
    "tokens_in": int, "tokens_out": int, "cost_usd": float,
    "iterations": int,     # tool_calls auto_execute loop count
  }
"""
from __future__ import annotations

import json as _json
import logging
import re
from typing import Any

from app.core.llm_router.router import calculate_cost, chat_completion
from app.core.pipeline.template import render_template
from app.core.tools.registry import tool_registry
from app.db import crud

logger = logging.getLogger(__name__)


def _resolve_system_prompt(cfg: dict, project_id: str) -> str:
    """Resolve system_prompt: ref_version_id > ref > raw text > empty."""
    ref_ver = cfg.get("system_prompt_ref_version")
    ref = cfg.get("system_prompt_ref")
    raw = cfg.get("system_prompt") or ""
    try:
        return crud.resolve_prompt(
            project_id=project_id,
            ref_version_id=ref_ver,
            ref=ref,
            raw_text=raw,
            fallback="",
        ) or ""
    except Exception as e:
        logger.warning("resolve_prompt failed, using raw: %s", e)
        return raw


def _extract_first_json(text: str) -> dict | None:
    """Find first balanced {...} or [...] block and parse. Tolerant of code fences / prose."""
    if not text:
        return None
    # Strip ```json ... ``` fence if present
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        candidate = fence.group(1).strip()
        try:
            return _json.loads(candidate)
        except (ValueError, TypeError):
            pass
    # Find first { or [
    for opener, closer in (("{", "}"), ("[", "]")):
        idx = text.find(opener)
        if idx < 0:
            continue
        depth = 0
        for i in range(idx, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    candidate = text[idx:i + 1]
                    try:
                        return _json.loads(candidate)
                    except (ValueError, TypeError):
                        break
    return None


def _accumulate_to_ctx(ctx: Any, model: str, tokens_in: int, tokens_out: int) -> float:
    """Accumulate tokens + cost into ctx aggregates and return this call's cost.

    Mirrors the legacy handle_call_model behaviour so total_tokens_in/out and
    total_cost_usd remain the source of truth for downstream consumers (compare
    endpoint, /chat metadata, pipeline_runs aggregate).
    """
    cost = calculate_cost(model, tokens_in, tokens_out)
    ctx.total_tokens_in += int(tokens_in or 0)
    ctx.total_tokens_out += int(tokens_out or 0)
    ctx.total_cost_usd += float(cost or 0)
    return cost


def _build_user_message(cfg: dict, ctx: Any) -> str:
    """Render user_prompt_template with variable substitution; default to ctx.user_message."""
    template = (cfg.get("user_prompt_template") or "").strip()
    if not template:
        return ctx.user_message or ""
    extra_roots = {
        "user_input": {"message": ctx.user_message or ""},
        "ctx": {
            "rag_context": ctx.rag_context or "",
            "history": ctx.history or [],
        },
    }
    return render_template(template, ctx.node_outputs, extra_roots=extra_roots)


def _build_tools_payload(tool_ids: list[str], project_id: str) -> tuple[list[dict], list[dict]]:
    """Return (litellm_tools, db_tools) for the configured tool_ids.

    Falls back to tenant-wide tools if tool_ids is empty.
    """
    if not tool_ids:
        return [], []
    db_tools: list[dict] = []
    for tid in tool_ids:
        try:
            t = crud.get_tool(tid)
        except Exception:
            t = None
        if t and t.get("is_active"):
            db_tools.append(t)
    if not db_tools:
        return [], []
    return tool_registry.convert_to_llm_tools(db_tools), db_tools


async def handle_model_call(node: dict, ctx: Any) -> dict:
    cfg = node.get("config") or {}
    model = cfg.get("model")
    if not model:
        return {"status": "error", "summary": "model is required", "error": "missing model"}

    output_format = (cfg.get("output_format") or "text").lower()
    temperature = float(cfg.get("temperature") or 0.7)
    max_tokens = int(cfg.get("max_tokens") or 2000)

    system_prompt = _resolve_system_prompt(cfg, ctx.project_id)
    user_message = _build_user_message(cfg, ctx)

    # Build messages: history (if available) + system + user
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    # JSON mode: append a strict-JSON instruction so models without native JSON support comply
    if output_format == "json":
        schema = cfg.get("output_schema")
        if schema:
            messages.append({
                "role": "system",
                "content": f"Output ONLY valid JSON matching this schema (no prose, no code fence):\n{_json.dumps(schema, ensure_ascii=False)}",
            })
        else:
            messages.append({"role": "system", "content": "Output ONLY valid JSON (no prose, no code fence)."})
    # Append history if explicitly requested via cfg.include_history
    if cfg.get("include_history") and ctx.history:
        messages.extend(ctx.history)
    messages.append({"role": "user", "content": user_message})

    output: dict[str, Any] = {
        "text": "",
        "json": None,
        "tool_calls": [],
        "tool_results": [],
        "model": model,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "iterations": 0,
    }

    # ── Mode dispatch ────────────────────────────────────────────────
    if output_format == "tool_calls":
        return await _run_tool_calls_mode(cfg, ctx, model, temperature, max_tokens, messages, output)

    # text / json modes
    retry_on_parse_fail = int(cfg.get("retry_on_parse_fail") or (1 if output_format == "json" else 0))
    last_error: str | None = None
    for attempt in range(1 + retry_on_parse_fail):
        try:
            resp = await chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tenant_id=getattr(ctx, "tenant_id", None),
                project_id=ctx.project_id,
                session_id=ctx.session_id,
                span_label=f"model_call/{output_format}",
            )
        except Exception as e:
            return {"status": "error", "summary": f"LLM 呼叫失敗: {e}", "error": str(e)}

        text = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        ti = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        to = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        output["tokens_in"] += ti
        output["tokens_out"] += to
        output["cost_usd"] += _accumulate_to_ctx(ctx, model, ti, to)
        output["text"] = text

        if output_format == "text":
            ctx.llm_response_text = text  # bubble to ctx for output node
            return {"status": "ok", "output": output, "summary": f"text · {len(text)} chars · ${output['cost_usd']:.4f}"}

        # JSON mode
        parsed = _extract_first_json(text)
        if parsed is not None:
            output["json"] = parsed
            keys_summary = list(parsed)[:5] if isinstance(parsed, dict) else 'array'
            return {"status": "ok", "output": output, "summary": f"json · keys={keys_summary} · ${output['cost_usd']:.4f}"}
        last_error = f"JSON parse failed; got: {text[:200]}"
        if attempt < retry_on_parse_fail:
            messages.append({"role": "user", "content": "Your last reply was not valid JSON. Please reply with ONLY valid JSON, no prose."})

    return {"status": "error", "summary": "JSON parse 失敗（重試耗盡）", "error": last_error or "unknown"}


async def _run_tool_calls_mode(
    cfg: dict, ctx: Any, model: str, temperature: float, max_tokens: int,
    messages: list[dict], output: dict,
) -> dict:
    tool_ids = cfg.get("tools") or []
    auto_execute = bool(cfg.get("auto_execute_tools", True))
    max_iter = int(cfg.get("max_iterations") or 10)

    llm_tools, db_tools = _build_tools_payload(tool_ids, ctx.project_id)
    if not llm_tools:
        # No tools configured → fall through to text mode
        try:
            resp = await chat_completion(
                messages=messages, model=model, temperature=temperature, max_tokens=max_tokens,
                tenant_id=getattr(ctx, "tenant_id", None),
                project_id=ctx.project_id, session_id=ctx.session_id,
                span_label="model_call/tool_calls(no_tools)",
            )
            text = (resp.choices[0].message.content or "").strip()
            usage = getattr(resp, "usage", None)
            ti = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
            to = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
            output["text"] = text
            output["tokens_in"] = ti
            output["tokens_out"] = to
            output["cost_usd"] = _accumulate_to_ctx(ctx, model, ti, to)
            ctx.llm_response_text = text
            return {"status": "ok", "output": output, "summary": f"no tools → text-only · ${output['cost_usd']:.4f}"}
        except Exception as e:
            return {"status": "error", "summary": f"LLM 呼叫失敗: {e}", "error": str(e)}

    # Tool-use loop
    final_text = ""
    for iteration in range(max_iter):
        output["iterations"] = iteration + 1
        try:
            resp = await chat_completion(
                messages=messages, model=model, temperature=temperature, max_tokens=max_tokens,
                tools=llm_tools,
                tenant_id=getattr(ctx, "tenant_id", None),
                project_id=ctx.project_id, session_id=ctx.session_id,
                span_label=f"model_call/tool_calls/iter{iteration + 1}",
            )
        except Exception as e:
            return {"status": "error", "summary": f"LLM 呼叫失敗 iter={iteration + 1}: {e}", "error": str(e)}

        msg = resp.choices[0].message
        usage = getattr(resp, "usage", None)
        ti = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        to = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        output["tokens_in"] += ti
        output["tokens_out"] += to
        output["cost_usd"] += _accumulate_to_ctx(ctx, model, ti, to)

        tool_calls = getattr(msg, "tool_calls", None) or []
        text_part = (msg.content or "").strip() if msg.content else ""
        if text_part:
            final_text = text_part

        # Stop conditions
        if not tool_calls:
            break
        if not auto_execute:
            # Surface tool_calls to downstream execute_tools node
            output["tool_calls"] = [
                {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                for tc in tool_calls
            ]
            break

        # Append assistant turn (with tool_calls) and execute each
        messages.append({
            "role": "assistant",
            "content": text_part or None,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        })
        for tc in tool_calls:
            try:
                params = _json.loads(tc.function.arguments or "{}")
            except (ValueError, TypeError):
                params = {}
            try:
                result = await tool_registry.execute_tool_by_name(
                    tc.function.name, params, db_tools,
                )
            except Exception as e:
                result = {"status": "error", "detail": str(e)}
            output["tool_results"].append({
                "iteration": iteration + 1,
                "name": tc.function.name,
                "params": params,
                "result": result,
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": _json.dumps(result, ensure_ascii=False)[:8000],
            })
        # next loop iteration

    output["text"] = final_text
    ctx.llm_response_text = final_text
    summary = f"tool_calls · iter={output['iterations']} · {len(output['tool_results'])} tools · ${output['cost_usd']:.4f}"
    return {"status": "ok", "output": output, "summary": summary}
