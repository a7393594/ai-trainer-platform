"""
Pipeline Studio — 管線追蹤與可視化層

每次走過 orchestrator 的 chat turn 都可選擇性建立一個 PipelineRun,
記錄經過的每個階段(input / context_loader / triage / router / tools / main_model / output)
的輸入輸出、延遲、成本。資料寫入 ait_pipeline_runs 表,供前端 /studio 頁面視覺化。

使用方式(orchestrator 端):

    from app.core.pipeline.tracer import pipeline_run_context

    async with pipeline_run_context(project_id, session_id, input_text) as run:
        run.add_span(...)   # 或透過 llm_router / tools 的 hook 隱式寫入
        ...
"""
from app.core.pipeline.tracer import (
    NodeSpan,
    PipelineRun,
    current_run,
    pipeline_run_context,
    record_llm_span,
    record_tool_span,
    start_process_span,
)

__all__ = [
    "NodeSpan",
    "PipelineRun",
    "current_run",
    "pipeline_run_context",
    "record_llm_span",
    "record_tool_span",
    "start_process_span",
]
