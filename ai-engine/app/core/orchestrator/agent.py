"""
Agent Orchestrator — AI Agent 的大腦

負責：
1. 接收使用者輸入
2. 意圖分類（匹配能力規則 / 進行中工作流 / 一般對話）
3. 分派到對應能力（元件 / 工具 / 工作流）
4. 組合最終回覆（文字 + 元件 + 工具結果）
"""
from typing import Optional
from app.models.schemas import (
    ChatRequest, ChatResponse, ChatMessage,
    WidgetResponse, Role,
)
from app.core.llm_router.router import chat_completion
from app.db import crud

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
        """意圖分類 — Phase 1 全部走一般對話"""
        # TODO Phase 3: 語意比對能力規則
        # TODO Phase 5: 工作流狀態檢查
        return {"type": "general"}

    async def _execute_capability(
        self, intent: dict, request: ChatRequest,
        session_id: str, history: list
    ) -> ChatResponse:
        """執行匹配到的能力規則"""
        # TODO Phase 3
        raise NotImplementedError("Phase 3")

    async def _continue_workflow(
        self, intent: dict, request: ChatRequest,
        session_id: str, history: list
    ) -> ChatResponse:
        """繼續進行中的工作流"""
        # TODO Phase 5
        raise NotImplementedError("Phase 5")

    async def _general_chat(
        self, request: ChatRequest, session_id: str, history: list
    ) -> ChatResponse:
        """一般 LLM 對話（Prompt + RAG）"""
        # 1. 先存 user message
        user_msg = crud.create_message(
            session_id=session_id,
            role="user",
            content=request.message,
        )

        # 2. 組合 LLM messages
        messages = []

        # System prompt
        system_prompt = await self._load_active_prompt(request.project_id)
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

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

        # 3. 呼叫 LLM
        model = request.model or "claude-sonnet-4-20250514"
        llm_response = await chat_completion(
            messages=messages,
            model=model,
        )

        # 4. 存 assistant message
        assistant_content = llm_response.choices[0].message.content
        assistant_msg = crud.create_message(
            session_id=session_id,
            role="assistant",
            content=assistant_content,
        )

        return ChatResponse(
            session_id=session_id,
            message=ChatMessage(role=Role.ASSISTANT, content=assistant_content),
            message_id=assistant_msg["id"],
        )

    async def _general_chat_with_history(
        self, session_id: str, history: list
    ) -> ChatResponse:
        """帶完整歷史的一般對話（用於元件回覆後繼續）"""
        llm_response = await chat_completion(messages=history)
        assistant_content = llm_response.choices[0].message.content

        assistant_msg = crud.create_message(
            session_id=session_id,
            role="assistant",
            content=assistant_content,
        )

        return ChatResponse(
            session_id=session_id,
            message=ChatMessage(role=Role.ASSISTANT, content=assistant_content),
            message_id=assistant_msg["id"],
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
