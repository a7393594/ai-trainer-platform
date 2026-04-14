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
from app.core.llm_router.router import chat_completion
from app.db import crud

# Widget 標記指示 — 附加到所有 system prompt
WIDGET_INSTRUCTION = """

## 互動元件指示（重要）
當你的回覆包含需要使用者做選擇、排序、或回答的問題時，請在回覆最末尾附上一個 JSON 標記，格式如下：

<!--WIDGET:{"type":"single_select","question":"問題文字","options":[{"id":"a","label":"選項A"},{"id":"b","label":"選項B"}]}-->

支援的 widget 類型：
- single_select：單選題（最常用，適合 A/B/C/D 選擇）
- multi_select：多選題（適合「選出所有正確答案」）
- rank：排序題（適合「由強到弱排列」）
- form：簡答題（適合開放式問題，fields: [{"id":"answer","label":"你的答案","type":"text"}]）
- confirm：是/否確認

規則：
- 只有當你主動向使用者提問、出題、或需要使用者做選擇時才使用
- 純講解性質的回覆不需要附加 widget
- JSON 標記必須放在回覆的最後一行
- 標記前的文字會正常顯示給使用者
- 不要在回覆正文中提到這個標記的存在
"""

# Demo user fallback
DEMO_USER_EMAIL = "demo@ai-trainer.dev"


class AgentOrchestrator:
    """
    Agent 調度器 — 每次使用者輸入都經過這裡
    """

    async def process(self, request: ChatRequest) -> ChatResponse:
        """處理一次使用者輸入的完整流程"""
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

        # 載入對話歷史
        history = await self._load_history(session_id)

        # 意圖分類
        intent = await self._classify_intent(request.message, request.project_id)

        # 根據意圖分派
        if intent["type"] == "capability_rule":
            return await self._execute_capability(intent, request, session_id, history)
        elif intent["type"] == "active_workflow":
            return await self._continue_workflow(intent, request, session_id, history)
        else:
            return await self._general_chat(request, session_id, history)

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
        """意圖分類 — 語意比對能力規則"""
        from app.core.intent.classifier import intent_classifier
        result = intent_classifier.classify(message, project_id)

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
                system_prompt = await self._load_active_prompt(request.project_id)
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
                    system_prompt = await self._load_active_prompt(request.project_id)
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
            # Start a workflow
            from app.core.workflows.engine import workflow_engine
            workflow_id = action_config.get("workflow_id")
            if workflow_id:
                user_id = request.user_id or "anonymous"
                result = await workflow_engine.start_workflow(workflow_id, session_id, user_id)
                if result.get("status") == "started":
                    text = f"已啟動工作流：{result.get('workflow_name', '')}。\n\n當前步驟：{result.get('current_step', {}).get('id', '')}"
                    assistant_msg = crud.create_message(
                        session_id=session_id, role="assistant", content=text,
                        metadata={"workflow_run_id": result.get("run_id"), "capability_rule_id": rule["id"]},
                    )
                    # If first step has a widget, include it
                    step = result.get("current_step", {})
                    widgets = [step.get("widget")] if step.get("widget") else []
                    return ChatResponse(
                        session_id=session_id,
                        message=ChatMessage(role=Role.ASSISTANT, content=text),
                        message_id=assistant_msg["id"],
                        widgets=widgets,
                    )

            return await self._general_chat(request, session_id, history)

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
        db_tools, llm_tools = await self._load_project_tools(request.project_id)

        # 3. 組合 LLM messages
        messages = []

        # System prompt + widget instruction
        system_prompt = await self._load_active_prompt(request.project_id)
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

        # 4. 呼叫 LLM（帶工具）
        model = request.model or "claude-sonnet-4-20250514"
        llm_response = await chat_completion(
            messages=messages,
            model=model,
            tools=llm_tools if llm_tools else None,
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

            # Execute tools
            tool_msgs, tool_results = await self._execute_tool_calls(llm_response, db_tools)
            all_tool_results.extend(tool_results)
            messages.extend(tool_msgs)

            # Re-invoke LLM with tool results
            llm_response = await chat_completion(
                messages=messages,
                model=model,
                tools=llm_tools if llm_tools else None,
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
    # 資料存取（接 Supabase）
    # ========================================

    async def _create_session(self, project_id: str, user_id: str) -> dict:
        """建立新的訓練會話"""
        return crud.create_session(project_id, user_id, "freeform")

    async def _load_history(self, session_id: str) -> list:
        """載入對話歷史，轉為 LLM 格式"""
        messages = crud.list_messages(session_id)
        return [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant")
        ]

    async def _load_active_prompt(self, project_id: str) -> Optional[str]:
        """載入專案目前使用的系統提示詞"""
        prompt = crud.get_active_prompt(project_id)
        return prompt["content"] if prompt else None

    async def _search_knowledge(self, query: str, project_id: str) -> Optional[str]:
        """從知識庫搜尋相關內容（RAG — pgvector 或 keyword fallback）"""
        try:
            results = crud.search_knowledge_chunks(project_id, query, limit=5)
            if results:
                context_parts = [r["content"] for r in results]
                return "\n\n---\n\n".join(context_parts)
        except Exception:
            pass
        return None
