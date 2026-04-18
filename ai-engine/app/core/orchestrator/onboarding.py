"""
Onboarding Manager -- 引導式建立 AI 基線

負責：
1. 從領域模板載入問題
2. 逐題引導使用者回答
3. 彙整答案後用 LLM 產出 System Prompt
4. 自動產出關鍵測試題（寫入 ait_eval_test_cases）
"""
import json

from app.models.schemas import ChatResponse, ChatMessage, OnboardingProgress, Role
from app.core.prompt.templates import get_template
from app.core.llm_router.router import chat_completion
from app.db import crud


DEFAULT_AUTO_QUESTION_COUNT = 12


class OnboardingManager:

    async def start_onboarding(
        self, project_id: str, user_id: str, template_id: str = "general"
    ) -> ChatResponse:
        """開始 Onboarding，回傳第一個問題"""
        template = get_template(template_id)
        if not template:
            template = get_template("general")
            template_id = "general"

        questions = template["questions"]

        # 建立 onboarding session
        session = crud.create_session(project_id, user_id, "onboarding")

        # 存系統訊息，記錄模板資訊
        crud.create_message(
            session_id=session["id"],
            role="system",
            content=f"Onboarding started with template: {template_id}",
            metadata={
                "template_id": template_id,
                "total_questions": len(questions),
                "question_ids": [q["id"] for q in questions],
            },
        )

        # 回傳第一題
        first_q = questions[0]
        return self._build_question_response(session["id"], first_q, 1, len(questions))

    async def handle_answer(
        self, session_id: str, question_id: str, answer: dict
    ) -> ChatResponse:
        """處理答案，回傳下一題或完成"""
        # 存答案
        crud.create_message(
            session_id=session_id,
            role="user",
            content=f"[Onboarding] {question_id}: {answer}",
            metadata={"question_id": question_id, "answer": answer},
        )

        # 取得模板資訊
        messages = crud.list_messages(session_id)
        system_msg = next(
            (m for m in messages if m["role"] == "system" and m["metadata"].get("template_id")),
            None,
        )
        if not system_msg:
            raise ValueError("Cannot find onboarding system message")

        template_id = system_msg["metadata"]["template_id"]
        question_ids = system_msg["metadata"]["question_ids"]
        total = system_msg["metadata"]["total_questions"]
        template = get_template(template_id)

        # 計算已回答數
        answered = [
            m["metadata"]["question_id"]
            for m in messages
            if m["role"] == "user" and m["metadata"].get("question_id")
        ]
        current = len(answered)

        # 還有下一題
        if current < total:
            next_q_id = question_ids[current]
            next_q = next(q for q in template["questions"] if q["id"] == next_q_id)
            return self._build_question_response(session_id, next_q, current + 1, total)

        # 全部回答完 -> 產出 Prompt
        return await self._complete_onboarding(session_id, messages, template)

    async def get_progress(self, session_id: str) -> OnboardingProgress:
        """取得 Onboarding 進度"""
        messages = crud.list_messages(session_id)
        system_msg = next(
            (m for m in messages if m["role"] == "system" and m["metadata"].get("template_id")),
            None,
        )
        if not system_msg:
            raise ValueError("Not an onboarding session")

        template_id = system_msg["metadata"]["template_id"]
        total = system_msg["metadata"]["total_questions"]
        answered = sum(
            1 for m in messages
            if m["role"] == "user" and m["metadata"].get("question_id")
        )

        return OnboardingProgress(
            session_id=session_id,
            current=answered,
            total=total,
            template_id=template_id,
            completed=answered >= total,
        )

    # ========================================
    # 內部方法
    # ========================================

    def _build_question_response(
        self, session_id: str, question: dict, current: int, total: int
    ) -> ChatResponse:
        """把模板問題轉成 ChatResponse + Widget"""
        widget = {
            "widget_type": question["widget_type"],
            "question": question["question"],
            "options": question.get("options", []),
            "config": question.get("config", {}),
            "allow_skip": not question.get("required", True),
        }

        return ChatResponse(
            session_id=session_id,
            message=ChatMessage(
                role=Role.ASSISTANT,
                content=f"({current}/{total}) {question['question']}",
            ),
            widgets=[widget],
            metadata={
                "onboarding": True,
                "question_id": question["id"],
                "progress": {"current": current, "total": total},
            },
        )

    async def _complete_onboarding(
        self, session_id: str, messages: list[dict], template: dict
    ) -> ChatResponse:
        """彙整答案 -> LLM 產出 System Prompt"""
        # 組合 Q&A 摘要
        qa_pairs = []
        question_map = {q["id"]: q["question"] for q in template["questions"]}

        for msg in messages:
            if msg["role"] == "user" and msg["metadata"].get("question_id"):
                q_id = msg["metadata"]["question_id"]
                answer = msg["metadata"].get("answer", {})
                q_text = question_map.get(q_id, q_id)
                qa_pairs.append(f"Q: {q_text}\nA: {answer}")

        qa_summary = "\n\n".join(qa_pairs)

        # 呼叫 LLM 產出 System Prompt
        llm_messages = [
            {
                "role": "system",
                "content": (
                    "你是一位 Prompt 工程專家。根據以下用戶訪談回答，產出一份完整的 AI 助手 System Prompt。\n\n"
                    "要求：\n"
                    "1. 包含：角色定義、語氣風格、回答範圍、能力、限制、回答格式\n"
                    "2. 用繁體中文撰寫\n"
                    "3. 結構清晰，使用 Markdown 格式\n"
                    "4. 只回傳 System Prompt 內容，不要其他說明"
                ),
            },
            {
                "role": "user",
                "content": f"以下是用戶的訪談回答：\n\n{qa_summary}",
            },
        ]

        llm_response = await chat_completion(messages=llm_messages, model="claude-sonnet-4-20250514")
        prompt_content = llm_response.choices[0].message.content

        # 取得 session 的 project_id
        session = crud.get_session(session_id)
        project_id = session["project_id"]

        # 存為 prompt_version
        version_num = crud.get_next_version_number(project_id)
        prompt_version = crud.create_prompt_version(
            project_id=project_id,
            content=prompt_content,
            version=version_num,
            is_active=True,
            change_notes=f"Onboarding ({template['id']}) auto-generated",
        )

        # 自動產出測試題（失敗不阻斷主流程）
        auto_tc_count = 0
        try:
            auto_tc_count = await self._generate_test_cases(
                project_id=project_id,
                prompt_content=prompt_content,
                qa_summary=qa_summary,
                count=DEFAULT_AUTO_QUESTION_COUNT,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] auto test case generation failed: {e}")

        # 存完成訊息
        crud.create_message(
            session_id=session_id,
            role="assistant",
            content="Onboarding complete! System Prompt has been generated.",
            metadata={
                "onboarding_complete": True,
                "prompt_version_id": prompt_version["id"],
                "prompt_version": version_num,
                "auto_test_cases": auto_tc_count,
            },
        )

        # 結束 session
        crud.end_session(session_id)

        return ChatResponse(
            session_id=session_id,
            message=ChatMessage(
                role=Role.ASSISTANT,
                content=(
                    f"基線建立完成！已自動產出 System Prompt (v{version_num})，"
                    f"並自動建立 {auto_tc_count} 筆測試題。\n\n"
                    f"---\n\n{prompt_content[:500]}{'...' if len(prompt_content) > 500 else ''}"
                ),
            ),
            metadata={
                "onboarding_complete": True,
                "prompt_version_id": prompt_version["id"],
                "prompt_preview": prompt_content[:1000],
                "auto_test_cases": auto_tc_count,
            },
        )

    async def _generate_test_cases(
        self,
        project_id: str,
        prompt_content: str,
        qa_summary: str,
        count: int,
    ) -> int:
        """以 Onboarding 收集到的背景 + 生成的 Prompt 為依據，產出測試題並寫入 DB。回傳寫入筆數。"""
        system = (
            "你是 AI 評估測試題產生器。根據下方提供的 System Prompt 與訪談摘要，"
            f"產生 {count} 筆涵蓋核心能力的測試案例。每筆含：\n"
            "  - input: 使用者會問的真實問題\n"
            "  - expected: AI 應如何回答的理想答案（簡短指導原則即可，不必完整回答）\n"
            "  - category: 能力分類（如 accuracy / empathy / boundary / format 等）\n"
            "\n只回傳 JSON 陣列，格式：[{\"input\":\"...\",\"expected\":\"...\",\"category\":\"...\"}]"
        )
        user = (
            f"=== System Prompt ===\n{prompt_content[:3000]}\n\n"
            f"=== 訪談摘要 ===\n{qa_summary[:2000]}"
        )
        resp = await chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            model="claude-sonnet-4-20250514",
            max_tokens=2500,
            temperature=0.3,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # 取出 JSON 陣列
        start = raw.find("[")
        end = raw.rfind("]")
        if start < 0 or end <= start:
            return 0
        try:
            items = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return 0

        saved = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            inp = (it.get("input") or "").strip()
            exp = (it.get("expected") or "").strip()
            if not inp or not exp:
                continue
            category = (it.get("category") or "onboarding_auto")[:50]
            try:
                crud.create_test_case(project_id, inp, exp, category)
                saved += 1
            except Exception:
                continue
        return saved
