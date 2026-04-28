"""
Tool: present_widget
Description: LLM 用來向使用者出示互動 widget(single_select / multi_select / form / structured_review / number_input)。
            前端從 tool_result 取出 widget dict 並渲染。
"""
from typing import Any

TOOL_NAME = "present_widget"

TOOL_DESCRIPTION = (
    "Show an interactive widget to the user. "
    "Use widget_type=single_select / multi_select for choosing among options, "
    "form / structured_review for multi-field input/review, "
    "number_input for numeric values. "
    "If blocking=true, the conversation pauses until the user responds. "
    "Return value is a 'widget' dict that the frontend will render."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "widget_type": {
            "type": "string",
            "enum": ["single_select", "multi_select", "form", "structured_review", "number_input"],
            "description": "Type of widget to display.",
        },
        "question": {
            "type": "string",
            "description": "Prompt text shown above the widget.",
        },
        "options": {
            "type": "array",
            "description": "For *_select: array of {id, label, is_default?}.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "is_default": {"type": "boolean"},
                },
                "required": ["id", "label"],
            },
        },
        "fields": {
            "type": "array",
            "description": "For form / structured_review: array of {name, label, input_type, default?, options?}.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "label": {"type": "string"},
                    "input_type": {"type": "string"},
                    "default": {},
                    "options": {"type": "array"},
                },
                "required": ["name", "label", "input_type"],
            },
        },
        "min": {"type": "number", "description": "For number_input: minimum value."},
        "max": {"type": "number", "description": "For number_input: maximum value."},
        "step": {"type": "number", "description": "For number_input: step granularity."},
        "default": {"description": "For number_input / form: default value."},
        "blocking": {
            "type": "boolean",
            "description": "If true, conversation halts until user responds (default false).",
            "default": False,
        },
    },
    "required": ["widget_type", "question"],
}


async def execute(
    params: dict,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Pack params into a widget dict for the frontend to render."""
    widget_type = params.get("widget_type")
    question = params.get("question", "")
    blocking = bool(params.get("blocking", False))

    widget: dict[str, Any] = {
        "type": widget_type,
        "question": question,
        "blocking": blocking,
    }

    # type-specific fields
    if widget_type in ("single_select", "multi_select"):
        widget["options"] = params.get("options", [])
    elif widget_type in ("form", "structured_review"):
        widget["fields"] = params.get("fields", [])
        if "default" in params:
            widget["default"] = params["default"]
    elif widget_type == "number_input":
        for key in ("min", "max", "step", "default"):
            if key in params:
                widget[key] = params[key]

    return {"widget": widget}
