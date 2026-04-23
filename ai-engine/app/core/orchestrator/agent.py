"""
Agent Orchestrator — AI Agent 的大腦

負責：
1. 接收使用者輸入
2. 意圖分類（匹配能力規則 / 進行中工作流 / 一般對話）
3. 分派到對應能力（元件 / 工具 / 工作流）
4. 組合最終回覆（文字 + 元件 + 工具結果）
5. 自動偵測回覆中的互動意圖並產生 Widget（Phase 3）
"""
import json
import re
from typing import Optional
from app.models.schemas import (
    ChatRequest, ChatResponse, ChatMessage,
    WidgetResponse, Role,
)
from app.core.llm_router.router import chat_completion, stream_chat_completion
from app.core.pipeline.tracer import (
    current_run,
    finish_span,
    pipeline_run_context,
    start_process_span,
)
from app.core.orchestrator import history as _history
from app.core.orchestrator import prompt_loader as _prompt_loader
from app.core.orchestrator.constants import WIDGET_INSTRUCTION, DEMO_USER_EMAIL
from app.db import crud


class AgentOrchestrator:
    """
    Agent 調度器 — 每次使用者輸入都經過這裡
    """

    async def process(self, request: ChatRequest) -> ChatResponse:
        """處理一次使用者輸入的完整流程（外層 + Pipeline Studio 追蹤）"""
        # 取得 user_id（如果沒提供，用 demo user）
        user_id = request.user_id
        if not user_id:
            demo_user = crud.get_user_by_email(DEMO_USER_EMAIL)
            if demo_user:
                user_id = demo_user["id"]
            else:
                raise ValueError("找不到 demo user，請先執行 seed")

        # 取得或建立會話
        session_id = request.session_id
        if not session_id:
            session = await self._create_session(
                request.project_id, user_id
            )
            session_id = session["id"]

        # 把整個 turn 包進 pipeline_run context — 追蹤器無副作用，寫不成也不影響主流程
        async with pipeline_run_context(
            project_id=request.project_id,
            session_id=session_id,
            input_text=request.message,
            mode="live",
            triggered_by=user_id,
        ):
            # input span
            input_span = start_process_span(
                label="user_input",
                input_ref={"message": request.message, "model": request.model},
                node_type="input",
            )
            finish_span(
                input_span,
                output_ref={"session_id": session_id, "user_id": user_id},
            )

            # context_loader: load history
            ctx_span = start_process_span(
                label="context_loader",
                input_ref={"session_id": session_id},
            )
            history = await self._load_history(session_id)
            finish_span(
                ctx_span,
                output_ref={"history_length": len(history)},
                metadata={"history_preview": history[-3:] if history else []},
            )

            # triage: intent classification (keyword matching today)
            triage_span = start_process_span(
                label="triage",
                input_ref={"message": request.message},
            )
            intent = await self._classify_intent(request.message, request.project_id)
            finish_span(
                triage_span,
                output_ref={
                    "type": intent.get("type"),
                    "matched": intent.get("rule", {}).get("trigger_description")
                    if intent.get("type") == "capability_rule"
                    else None,
                },
            )

            # router: dispatch
            router_span = start_process_span(
                label="router",
                input_ref={"intent_type": intent.get("type")},
            )

            try:
                if intent["type"] == "capability_rule":
                    finish_span(router_span, output_ref={"branch": "capability"})
                    result = await self._execute_capability(
                        intent, request, session_id, history
                    )
                elif intent["type"] == "active_workflow":
                    finish_span(router_span, output_ref={"branch": "workflow"})
                    result = await self._continue_workflow(
                        intent, request, session_id, history
                    )
                else:
                    finish_span(router_span, output_ref={"branch": "general"})
                    result = await self._general_chat(request, session_id, history)
            except Exception as e:
                finish_span(router_span, status="error", error=str(e))
                raise

            # output span — link the final assistant message back to the pipeline run
            run = current_run()
            if run is not None and result is not None:
                run.message_id = getattr(result, "message_id", None)

            out_span = start_process_span(
                label="output",
                input_ref={
                    "widgets": len(getattr(result, "widgets", []) or []),
                    "tool_results": len(getattr(result, "tool_results", []) or []),
                },
                node_type="output",
            )
            finish_span(
                out_span,
                output_ref={
                    "message_id": getattr(result, "message_id", None),
                    "content_preview": (
                        getattr(result.message, "content", "")[:200]
                        if result and getattr(result, "message", None)
                        else ""
                    ),
                },
            )
            return result

    async def handle_widget_result(self, response: WidgetResponse) -> ChatResponse:
        """處理使用者對互動元件的操作結果"""
        session_id = response.session_id
        history = await self._load_history(session_id)

        # 把元件結果存入訊息歷史
        widget_msg = crud.create_message(
            session_id=session_id,
            role="user",
            content=f"[Widget Response] {response.result}",
            metadata={"widget_type": response.widget_type, "result": response.result},
        )

        history.append({"role": "user", "content": widget_msg["content"]})

        return await self._general_chat_with_history(session_id, history)

    # ========================================
    # 內部方法
    # ========================================

    async def _classify_intent(self, message: str, project_id: str) -> dict:
        """意圖分類 — keyword + 語意 embedding (hybrid) 比對能力規則"""
        from app.core.intent.classifier import intent_classifier
        result = await intent_classifier.classify_async(message, project_id, mode="hybrid")

        # Check for active workflow (Phase 5)
        # TODO: check if user has an active workflow_run in waiting_input state

        return result

    async def _execute_capability(
        self, intent: dict, request: ChatRequest,
        session_id: str, history: list
    ) -> ChatResponse:
        """執行匹配到的能力規則"""
        rule = intent["rule"]
        action_type = rule["action_type"]
        action_config = rule.get("action_config", {})

        # Save user message
        crud.create_message(session_id=session_id, role="user", content=request.message)

        if action_type == "widget":
            # Return widget definition in response
            widget_def = action_config.get("widget", {})
            # Also generate a text response via LLM for context
            text_response = action_config.get("text", "")
            if not text_response:
                # Generate contextual text with LLM
                system_prompt = await self._load_active_prompt(request.project_id, session_id)
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.extend(history)
                messages.append({"role": "user", "content": request.message})
                messages.append({"role": "system", "content": f"使用者的問題匹配到了一個互動元件規則。請用自然語言回覆使用者，然後系統會自動顯示互動元件。規則描述：{rule['trigger_description']}"})
                llm_response = await chat_completion(messages=messages, model=request.model or "claude-sonnet-4-20250514")
                text_response = llm_response.choices[0].message.content

            assistant_msg = crud.create_message(
                session_id=session_id, role="assistant", content=text_response,
                metadata={"capability_rule_id": rule["id"], "action_type": action_type},
            )

            return ChatResponse(
                session_id=session_id,
                message=ChatMessage(role=Role.ASSISTANT, content=text_response),
                message_id=assistant_msg["id"],
                widgets=[widget_def] if widget_def else [],
            )

        elif action_type == "tool_call":
            # Execute registered tool
            tool_id = action_config.get("tool_id")
            if tool_id:
                tool = crud.get_tool(tool_id)
                if tool:
                    # For now, include tool info in LLM context
                    system_prompt = await self._load_active_prompt(request.project_id, session_id)
                    messages = []
                    if system_prompt:
                        messages.append({"role": "system", "content": system_prompt})
                    messages.extend(history)
                    messages.append({"role": "user", "content": request.message})
                    messages.append({"role": "system", "content": f"可用工具：{tool['name']} — {tool['description']}。請使用此工具回答使用者。"})
                    llm_response = await chat_completion(messages=messages, model=request.model or "claude-sonnet-4-20250514")
                    text_response = llm_response.choices[0].message.content

                    assistant_msg = crud.create_message(
                        session_id=session_id, role="assistant", content=text_response,
                        metadata={"capability_rule_id": rule["id"], "tool_id": tool_id},
                    )
                    return ChatResponse(
                        session_id=session_id,
                        message=ChatMessage(role=Role.ASSISTANT, content=text_response),
                        message_id=assistant_msg["id"],
                        tool_results=[{"tool_name": tool["name"], "status": "referenced"}],
                    )

            # Fallback to general chat if tool not found
            return await self._general_chat(request, session_id, history)

        elif action_type == "workflow":
            # Trigger a workflow. `run_mode: auto` 一次跑到結束（適合純自動化流程）；
            # 其它值走步進式，讓使用者逐步推進（含 widget 互動）。
            from app.core.workflows.engine import workflow_engine
            workflow_id = action_config.get("workflow_id")
            run_mode = action_config.get("run_mode", "step")
            if not workflow_id:
                return await self._general_chat(request, session_id, history)

            user_id = request.user_id or "anonymous"

            if run_mode == "auto":
                result = await workflow_engine.run_to_completion(
                    workflow_id,
                    session_id=session_id,
                    user_id=user_id,
                    initial_vars={"message": request.message},
                )
                status = result.get("status")
                trace_len = len(result.get("trace") or [])
                if status == "completed":
                    text = f"工作流已自動執行完成（{trace_len} 個步驟）。"
                else:
                    text = f"工作流執行失敗：{result.get('error', 'unknown')}"
                assistant_msg = crud.create_message(
                    session_id=session_id, role="assistant", content=text,
                    metadata={
                        "workflow_run_id": result.get("run_id"),
                        "capability_rule_id": rule["id"],
                        "workflow_status": status,
                        "workflow_vars": result.get("vars"),
                    },
                )
                return ChatResponse(
                    session_id=session_id,
                    message=ChatMessage(role=Role.ASSISTANT, content=text),
                    message_id=assistant_msg["id"],
                    metadata={"workflow_status": status, "workflow_run_id": result.get("run_id")},
                )

            # 步進式（原本行為）
            result = await workflow_engine.start_workflow(workflow_id, session_id, user_id)
            if result.get("status") == "started":
                text = f"已啟動工作流：{result.get('workflow_name', '')}。\n\n當前步驟：{result.get('current_step', {}).get('id', '')}"
                assistant_msg = crud.create_message(
                    session_id=session_id, role="assistant", content=text,
                    metadata={"workflow_run_id": result.get("run_id"), "capability_rule_id": rule["id"]},
                )
                step = result.get("current_step", {})
                widgets = [step.get("widget")] if step.get("widget") else []
                return ChatResponse(
                    session_id=session_id,
                    message=ChatMessage(role=Role.ASSISTANT, content=text),
                    message_id=assistant_msg["id"],
                    widgets=widgets,
                )

            return await self._general_chat(request, session_id, history)

        elif action_type == "handoff":
            # 自動升級至真人客服
            from app.core.handoff.service import handoff_service

            reason = action_config.get("reason") or "User triggered handoff capability"
            urgency = action_config.get("urgency", "normal")
            result = await handoff_service.request(
                session_id, reason=reason, triggered_by="capability_rule", urgency=urgency,
            )
            reply = action_config.get("text") or "已為您轉接真人客服，稍後會有專員與您聯繫。"
            assistant_msg = crud.create_message(
                session_id=session_id, role="assistant", content=reply,
                metadata={
                    "capability_rule_id": rule["id"],
                    "handoff_message_id": result.get("handoff_message_id"),
                    "handoff_notified": result.get("notified"),
                    "handoff_urgency": urgency,
                },
            )
            return ChatResponse(
                session_id=session_id,
                message=ChatMessage(role=Role.ASSISTANT, content=reply),
                message_id=assistant_msg["id"],
                metadata={
                    "handoff": True,
                    "handoff_message_id": result.get("handoff_message_id"),
                    "urgency": urgency,
                },
            )

        else:
            # composite or unknown — fallback to general chat
            return await self._general_chat(request, session_id, history)

    async def _continue_workflow(
        self, intent: dict, request: ChatRequest,
        session_id: str, history: list
    ) -> ChatResponse:
        """繼續進行中的工作流"""
        # TODO Phase 5: check active workflow_run, advance with user response
        return await self._general_chat(request, session_id, history)

    def _parse_widget_from_response(self, content: str) -> tuple[str, list[dict]]:
        """解析回覆中的 <!--WIDGET:...--> 標記，拆分為文字和 widget 列表"""
        widgets = []
        pattern = r'<!--WIDGET:(.*?)-->'
        matches = re.findall(pattern, content, re.DOTALL)

        clean_text = re.sub(pattern, '', content).strip()

        for match in matches:
            try:
                widget_data = json.loads(match.strip())
                # Normalize to WidgetDefinition format
                widget = {
                    "widget_type": widget_data.get("type", "single_select"),
                    "question": widget_data.get("question", ""),
                    "options": widget_data.get("options", []),
                    "config": widget_data.get("config", {}),
                    "allow_skip": widget_data.get("allow_skip", False),
                }
                # Add fields for form type
                if widget_data.get("fields"):
                    widget["config"]["fields"] = widget_data["fields"]
                widgets.append(widget)
            except (json.JSONDecodeError, KeyError):
                pass

        return clean_text, widgets

    async def _load_project_tools(self, project_id: str) -> tuple[list[dict], list[dict]]:
        """載入專案可用工具，回傳 (db_tools, llm_tools)"""
        from app.core.tools.registry import tool_registry
        # Tools are tenant-level; get tenant from project
        project = crud.get_project(project_id)
        if not project:
            return [], []
        tenant_id = project.get("tenant_id")
        if not tenant_id:
            return [], []
        db_tools = await tool_registry.list_tools(tenant_id)
        llm_tools = tool_registry.convert_to_llm_tools(db_tools)
        return db_tools, llm_tools

    async def _execute_tool_calls(self, response, db_tools: list[dict]) -> tuple[list[dict], list[dict]]:
        """解析 LLM 回覆中的 tool_calls，執行工具，回傳 (tool_messages, tool_results)"""
        from app.core.tools.registry import tool_registry
        tool_messages = []
        tool_results = []

        tool_calls = getattr(response.choices[0].message, 'tool_calls', None) or []
        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
            except json.JSONDecodeError:
                fn_args = {}

            # Execute via registry
            result = await tool_registry.execute_tool_by_name(fn_name, fn_args, db_tools)

            # Parse result data
            result_data = result.get("data", result)
            if isinstance(result_data, str):
                try:
                    result_data = json.loads(result_data)
                except json.JSONDecodeError:
                    pass

            tool_results.append({"tool_name": fn_name, "input": fn_args, "result": result_data, "status": result.get("status", "success")})

            # Build tool result message for LLM
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result_data, ensure_ascii=False) if not isinstance(result_data, str) else result_data,
            })

        return tool_messages, tool_results

    async def _general_chat(
        self, request: ChatRequest, session_id: str, history: list
    ) -> ChatResponse:
        """一般 LLM 對話（Prompt + RAG + 工具調用 + Widget 自動偵測）"""
        # 1. 先存 user message
        user_msg = crud.create_message(
            session_id=session_id,
            role="user",
            content=request.message,
        )

        # 2. 載入工具
        tools_span = start_process_span(
            label="load_tools",
            input_ref={"project_id": request.project_id},
        )
        db_tools, llm_tools = await self._load_project_tools(request.project_id)
        finish_span(
            tools_span,
            output_ref={"tool_count": len(db_tools), "llm_tool_count": len(llm_tools)},
        )

        # 3. 組合 LLM messages（coaching_core stage — 組 prompt + RAG + 歷史）
        compose_span = start_process_span(
            label="prompt_compose",
            input_ref={"message": request.message},
        )
        messages = []

        # System prompt + widget instruction (may apply A/B variant when session_id present)
        system_prompt = await self._load_active_prompt(request.project_id, session_id)
        full_system = (system_prompt or "") + WIDGET_INSTRUCTION
        messages.append({"role": "system", "content": full_system})

        # RAG context
        rag_context = await self._search_knowledge(request.message, request.project_id)
        if rag_context:
            messages.append({
                "role": "system",
                "content": f"以下是相關參考資料：\n\n{rag_context}",
            })

        # 對話歷史
        messages.extend(history)

        # 當前訊息
        messages.append({"role": "user", "content": request.message})
        finish_span(
            compose_span,
            output_ref={
                "message_count": len(messages),
                "has_rag": bool(rag_context),
                "system_prompt_length": len(full_system),
            },
        )

        # 4. 呼叫 LLM（帶工具 + 成本追蹤）
        # Model priority: request > pipeline config > project default > global default
        project = crud.get_project(request.project_id)
        # Batch 4B: per-project per-node pipeline config
        main_cfg = crud.get_node_config(request.project_id, "main_model") or {}
        model = (
            request.model
            or main_cfg.get("model")
            or (project.get("default_model") if project else None)
            or "claude-sonnet-4-20250514"
        )
        temperature = main_cfg.get("temperature", 0.7)
        max_tokens = main_cfg.get("max_tokens", 2000)

        # Filter tools by config's whitelist if set
        effective_tools = llm_tools
        tool_whitelist = main_cfg.get("tool_ids")
        if tool_whitelist is not None and llm_tools:
            allowed = set(tool_whitelist)
            # db_tools has id field; llm_tools is converted format - filter db_tools then reconvert
            filtered_db = [t for t in db_tools if t.get("id") in allowed]
            effective_tools = tool_registry.convert_to_llm_tools(filtered_db) if filtered_db else None

        llm_response = await chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=effective_tools if effective_tools else None,
            project_id=request.project_id,
            session_id=session_id,
            span_label="main_model",
        )

        # 5. 工具調用迴圈
        all_tool_results = []
        loop_count = 0
        MAX_TOOL_LOOPS = 5

        while loop_count < MAX_TOOL_LOOPS:
            tool_calls = getattr(llm_response.choices[0].message, 'tool_calls', None)
            if not tool_calls:
                break

            loop_count += 1

            # Add assistant message with tool calls to history
            messages.append(llm_response.choices[0].message)

            # Execute tools (tracer hook inside execute_tool_by_name writes one span per tool)
            tools_parallel_span = start_process_span(
                label=f"tools_iteration_{loop_count}",
                input_ref={"tool_calls": len(tool_calls)},
                node_type="parallel",
            )
            tool_msgs, tool_results = await self._execute_tool_calls(llm_response, db_tools)
            finish_span(
                tools_parallel_span,
                output_ref={
                    "tool_count": len(tool_results),
                    "statuses": [t.get("status") for t in tool_results],
                },
            )
            all_tool_results.extend(tool_results)
            messages.extend(tool_msgs)

            # Re-invoke LLM with tool results (same config as first call)
            llm_response = await chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=effective_tools if effective_tools else None,
                project_id=request.project_id,
                session_id=session_id,
                span_label=f"main_model_iter_{loop_count + 1}",
            )

        # 6. 解析最終回覆中的 widget 標記
        raw_content = llm_response.choices[0].message.content or ""
        clean_text, widgets = self._parse_widget_from_response(raw_content)

        # 7. 存 assistant message
        metadata = {}
        if widgets:
            metadata["widgets"] = widgets
        if all_tool_results:
            metadata["tool_results"] = all_tool_results

        assistant_msg = crud.create_message(
            session_id=session_id,
            role="assistant",
            content=clean_text,
            metadata=metadata,
        )

        return ChatResponse(
            session_id=session_id,
            message=ChatMessage(role=Role.ASSISTANT, content=clean_text),
            message_id=assistant_msg["id"],
            widgets=widgets,
            tool_results=all_tool_results,
        )

    async def _general_chat_with_history(
        self, session_id: str, history: list
    ) -> ChatResponse:
        """帶完整歷史的一般對話（用於元件回覆後繼續）"""
        llm_response = await chat_completion(messages=history)
        raw_content = llm_response.choices[0].message.content
        clean_text, widgets = self._parse_widget_from_response(raw_content)

        assistant_msg = crud.create_message(
            session_id=session_id,
            role="assistant",
            content=clean_text,
            metadata={"widgets": widgets} if widgets else {},
        )

        return ChatResponse(
            session_id=session_id,
            message=ChatMessage(role=Role.ASSISTANT, content=clean_text),
            message_id=assistant_msg["id"],
            widgets=widgets,
        )

    # ========================================
    # Streaming 版本 — 供 /chat/stream 使用
    # 與 process() 同樣被 Pipeline Studio 追蹤,但主模型呼叫改用 streaming。
    # 注意:streaming 模式不支援工具呼叫(tool_calls 與 streaming 語意衝突)。
    # ========================================

    async def process_stream(self, request: ChatRequest):
        """Async generator,yield dict 事件給 /chat/stream endpoint。

        事件類型:
          {"session_id": "..."}                      — 最先送出
          {"content": "chunk text"}                  — 每次 LLM 產出 chunk
          {"done": True, "message_id": "..."}        — 結束
          {"error": "..."}                           — 錯誤
        """
        # 取得 user_id
        user_id = request.user_id
        if not user_id:
            demo_user = crud.get_user_by_email(DEMO_USER_EMAIL)
            if demo_user:
                user_id = demo_user["id"]
            else:
                yield {"error": "找不到 demo user"}
                return

        # session
        session_id = request.session_id
        if not session_id:
            session = await self._create_session(request.project_id, user_id)
            session_id = session["id"]

        # 送出 session_id 給 client(比 pipeline 追蹤還早)
        yield {"session_id": session_id}

        # 包進 pipeline_run_context
        async with pipeline_run_context(
            project_id=request.project_id,
            session_id=session_id,
            input_text=request.message,
            mode="live",
            triggered_by=user_id,
        ):
            try:
                # input span
                input_span = start_process_span(
                    label="user_input",
                    input_ref={"message": request.message, "model": request.model, "streaming": True},
                    node_type="input",
                )
                finish_span(
                    input_span,
                    output_ref={"session_id": session_id, "user_id": user_id},
                )

                # 儲存使用者訊息
                crud.create_message(session_id=session_id, role="user", content=request.message)

                # context_loader
                ctx_span = start_process_span(
                    label="context_loader",
                    input_ref={"session_id": session_id},
                )
                history = await self._load_history(session_id)
                finish_span(ctx_span, output_ref={"history_length": len(history)})

                # triage(streaming 模式下仍走 general 分支,不處理 capability/workflow)
                triage_span = start_process_span(
                    label="triage",
                    input_ref={"message": request.message},
                )
                finish_span(
                    triage_span,
                    output_ref={"type": "general", "note": "streaming bypasses capability/workflow routing"},
                )

                # prompt_compose(coaching_core)
                compose_span = start_process_span(
                    label="prompt_compose",
                    input_ref={"message": request.message},
                )
                messages: list[dict] = []

                # 檢查是否為 poker_coach 專案 → 使用三層 prompt
                _project_check = crud.get_project(request.project_id)
                _ptype = (_project_check or {}).get("project_type", "trainer")

                if _ptype == "poker_coach":
                    from app.core.poker.prompt_builder import build_system_prompt as poker_build
                    from app.core.poker.student_model import get_profile_for_prompt
                    _pdata = get_profile_for_prompt(request.user_id or "", request.project_id)
                    _poker_sys = poker_build(
                        profile=_pdata["profile"] if _pdata else None,
                        mastery_summary=_pdata["mastery_summary"] if _pdata else None,
                    )
                    full_system = _poker_sys + WIDGET_INSTRUCTION
                else:
                    system_prompt = await self._load_active_prompt(request.project_id, session_id)
                    full_system = (system_prompt or "") + WIDGET_INSTRUCTION

                messages.append({"role": "system", "content": full_system})

                rag_context = await self._search_knowledge(request.message, request.project_id)
                if rag_context:
                    messages.append({
                        "role": "system",
                        "content": f"以下是相關參考資料：\n\n{rag_context}",
                    })

                messages.extend(history)
                messages.append({"role": "user", "content": request.message})
                finish_span(
                    compose_span,
                    output_ref={
                        "message_count": len(messages),
                        "has_rag": bool(rag_context),
                        "system_prompt_length": len(full_system),
                    },
                )

                # main_model 用 streaming — 套用 pipeline config
                project = crud.get_project(request.project_id)
                main_cfg = crud.get_node_config(request.project_id, "main_model") or {}
                model = (
                    request.model
                    or main_cfg.get("model")
                    or (project.get("default_model") if project else None)
                    or "claude-sonnet-4-20250514"
                )
                temperature = main_cfg.get("temperature", 0.7)
                max_tokens = main_cfg.get("max_tokens", 2000)

                full_content = ""
                async for chunk in stream_chat_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    project_id=request.project_id,
                    session_id=session_id,
                    span_label="main_model",
                ):
                    full_content += chunk
                    yield {"content": chunk}

                # 存 assistant message
                assistant_msg = crud.create_message(
                    session_id=session_id,
                    role="assistant",
                    content=full_content,
                )

                # output span
                run = current_run()
                if run is not None:
                    run.message_id = assistant_msg["id"]
                out_span = start_process_span(
                    label="output",
                    input_ref={"stream": True},
                    node_type="output",
                )
                finish_span(
                    out_span,
                    output_ref={
                        "message_id": assistant_msg["id"],
                        "content_preview": full_content[:200],
                    },
                )

                yield {"done": True, "message_id": assistant_msg["id"]}
            except Exception as e:
                yield {"error": str(e)}

    # ========================================
    # 資料存取（接 Supabase）
    # ========================================

    async def _create_session(self, project_id: str, user_id: str) -> dict:
        """建立新的訓練會話。超過方案上限時會丟 LimitExceeded。"""
        from app.core.plan.limits import plan_limits_service

        project = crud.get_project(project_id)
        tenant_id = (project or {}).get("tenant_id")
        if tenant_id:
            try:
                plan_limits_service.enforce_session_create(tenant_id)
            except Exception as e:  # LimitExceeded 或 DB 錯誤都不阻斷到崩潰
                if e.__class__.__name__ == "LimitExceeded":
                    raise
        return crud.create_session(project_id, user_id, "freeform")

    # 歷史壓縮參數 — 保留 class attribute 以維持既有引用
    HISTORY_COMPRESS_THRESHOLD = _history.HISTORY_COMPRESS_THRESHOLD
    HISTORY_KEEP_RECENT = _history.HISTORY_KEEP_RECENT

    # 壓縮計數器：指向 history 模組的 module-level dict
    # analytics endpoint 透過 AgentOrchestrator.compression_stats 讀取（__init__.py:1334-1337）
    compression_stats = _history.compression_stats

    async def _load_history(self, session_id: str, exclude_last_user: bool = True) -> list:
        return await _history.load_history(session_id, exclude_last_user=exclude_last_user)

    async def _compress_history_head(self, head: list[dict]) -> Optional[str]:
        return await _history.compress_history_head(head)

    async def _load_active_prompt(
        self,
        project_id: str,
        session_id: Optional[str] = None,
        prompt_override: Optional[str] = None,
    ) -> Optional[str]:
        return await _prompt_loader.load_active_prompt(project_id, session_id, prompt_override)

    async def _search_knowledge(self, query: str, project_id: str) -> Optional[str]:
        return await _prompt_loader.search_knowledge(query, project_id)
