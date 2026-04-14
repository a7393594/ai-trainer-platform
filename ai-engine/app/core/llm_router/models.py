"""
Centralized Model Registry — Single source of truth for all LLM models.

All model definitions, pricing, and metadata live here.
Other modules (router, comparison engine, API, frontend) reference this.
"""

MODELS = [
    # ═══════════════════════════════════════════
    # Anthropic (付費)
    # ═══════════════════════════════════════════
    {"id": "claude-sonnet-4-20250514", "label": "Claude Sonnet 4", "provider": "anthropic", "tier": "paid", "input_cost": 3.0, "output_cost": 15.0, "context": 200000, "tool_use": True, "tags": ["smart", "balanced"]},
    {"id": "claude-opus-4-20250514", "label": "Claude Opus 4", "provider": "anthropic", "tier": "paid", "input_cost": 15.0, "output_cost": 75.0, "context": 200000, "tool_use": True, "tags": ["smartest", "expensive"]},
    {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5", "provider": "anthropic", "tier": "paid", "input_cost": 0.8, "output_cost": 4.0, "context": 200000, "tool_use": True, "tags": ["fast", "cheap"]},

    # ═══════════════════════════════════════════
    # OpenAI (付費)
    # ═══════════════════════════════════════════
    {"id": "gpt-4o", "label": "GPT-4o", "provider": "openai", "tier": "paid", "input_cost": 2.5, "output_cost": 10.0, "context": 128000, "tool_use": True, "tags": ["smart", "multimodal"]},
    {"id": "gpt-4o-mini", "label": "GPT-4o Mini", "provider": "openai", "tier": "paid", "input_cost": 0.15, "output_cost": 0.6, "context": 128000, "tool_use": True, "tags": ["fast", "cheap"]},
    {"id": "o3-mini", "label": "o3-mini (Reasoning)", "provider": "openai", "tier": "paid", "input_cost": 1.1, "output_cost": 4.4, "context": 200000, "tool_use": True, "tags": ["reasoning"]},

    # ═══════════════════════════════════════════
    # Google (免費額度)
    # ═══════════════════════════════════════════
    {"id": "gemini/gemini-2.0-flash", "label": "Gemini 2.0 Flash", "provider": "google", "tier": "free-tier", "input_cost": 0.075, "output_cost": 0.3, "context": 1000000, "tool_use": True, "tags": ["fast", "huge-context"]},
    {"id": "gemini/gemini-2.5-flash-preview-04-17", "label": "Gemini 2.5 Flash", "provider": "google", "tier": "free-tier", "input_cost": 0.15, "output_cost": 0.6, "context": 1000000, "tool_use": True, "tags": ["smart", "huge-context"]},

    # ═══════════════════════════════════════════
    # Groq (免費，LPU 超快推理)
    # ═══════════════════════════════════════════
    {"id": "groq/llama-3.3-70b-versatile", "label": "Llama 3.3 70B (Groq)", "provider": "groq", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 128000, "tool_use": True, "tags": ["free", "fast", "open-source"]},
    {"id": "groq/llama-4-scout-17b-16e-instruct", "label": "Llama 4 Scout 17B (Groq)", "provider": "groq", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 131072, "tool_use": True, "tags": ["free", "fast", "open-source"]},
    {"id": "groq/qwen-qwq-32b", "label": "Qwen QwQ 32B (Groq)", "provider": "groq", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 131072, "tool_use": False, "tags": ["free", "reasoning", "open-source"]},
    {"id": "groq/deepseek-r1-distill-llama-70b", "label": "DeepSeek R1 70B (Groq)", "provider": "groq", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 131072, "tool_use": False, "tags": ["free", "reasoning", "open-source"]},
    {"id": "groq/mistral-saba-24b", "label": "Mistral Saba 24B (Groq)", "provider": "groq", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 32768, "tool_use": True, "tags": ["free", "fast", "open-source"]},
    {"id": "groq/gemma2-9b-it", "label": "Gemma 2 9B (Groq)", "provider": "groq", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 8192, "tool_use": False, "tags": ["free", "small", "open-source"]},
    {"id": "groq/llama-3.1-8b-instant", "label": "Llama 3.1 8B (Groq)", "provider": "groq", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 131072, "tool_use": True, "tags": ["free", "fast", "small"]},

    # ═══════════════════════════════════════════
    # DeepSeek (極低成本)
    # ═══════════════════════════════════════════
    {"id": "deepseek/deepseek-chat", "label": "DeepSeek V3", "provider": "deepseek", "tier": "low-cost", "input_cost": 0.27, "output_cost": 1.1, "context": 64000, "tool_use": True, "tags": ["smart", "cheap", "open-source"]},
    {"id": "deepseek/deepseek-reasoner", "label": "DeepSeek R1", "provider": "deepseek", "tier": "low-cost", "input_cost": 0.55, "output_cost": 2.19, "context": 64000, "tool_use": False, "tags": ["reasoning", "cheap", "open-source"]},

    # ═══════════════════════════════════════════
    # OpenRouter 免費模型
    # ═══════════════════════════════════════════
    {"id": "openrouter/deepseek/deepseek-r1:free", "label": "DeepSeek R1 (Free)", "provider": "openrouter", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 163840, "tool_use": False, "tags": ["free", "reasoning"]},
    {"id": "openrouter/qwen/qwen3-coder-480b:free", "label": "Qwen3 Coder 480B (Free)", "provider": "openrouter", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 262144, "tool_use": False, "tags": ["free", "coding", "huge"]},
    {"id": "openrouter/meta-llama/llama-3.3-70b-instruct:free", "label": "Llama 3.3 70B (Free)", "provider": "openrouter", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 131072, "tool_use": False, "tags": ["free", "open-source"]},
    {"id": "openrouter/mistralai/devstral-small:free", "label": "Devstral Small (Free)", "provider": "openrouter", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 131072, "tool_use": False, "tags": ["free", "coding"]},
    {"id": "openrouter/nvidia/llama-3.1-nemotron-70b-instruct:free", "label": "Nemotron 70B (Free)", "provider": "openrouter", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 131072, "tool_use": False, "tags": ["free", "open-source"]},
    {"id": "openrouter/google/gemini-2.0-flash-exp:free", "label": "Gemini 2.0 Flash Exp (Free)", "provider": "openrouter", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 1048576, "tool_use": False, "tags": ["free", "huge-context"]},
    {"id": "openrouter/google/gemma-4-26b-a4b-it:free", "label": "Gemma 4 26B A4B (Free)", "provider": "openrouter", "tier": "free", "input_cost": 0, "output_cost": 0, "context": 256000, "tool_use": True, "tags": ["free", "multimodal", "reasoning", "open-source", "MoE"]},
]


def get_model_pricing() -> dict[str, dict]:
    """Get pricing lookup: model_id → {input, output}"""
    return {m["id"]: {"input": m["input_cost"], "output": m["output_cost"]} for m in MODELS}


def get_model_by_id(model_id: str) -> dict | None:
    """Get a model definition by ID"""
    return next((m for m in MODELS if m["id"] == model_id), None)


def get_models_for_api() -> list[dict]:
    """Get model list formatted for /models API endpoint"""
    return [
        {
            "id": m["id"],
            "label": m["label"],
            "provider": m["provider"],
            "tier": m["tier"],
            "context": m["context"],
            "tool_use": m["tool_use"],
            "tags": m.get("tags", []),
            "cost": f"${m['input_cost']}/{m['output_cost']}" if m["input_cost"] > 0 else "Free",
        }
        for m in MODELS
    ]


def get_models_by_tier(tier: str) -> list[dict]:
    """Get models filtered by tier (free, free-tier, low-cost, paid)"""
    return [m for m in MODELS if m["tier"] == tier]
