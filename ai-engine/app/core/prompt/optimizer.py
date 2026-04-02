"""
Prompt Optimizer -- 根據使用者回饋自動產出 Prompt 優化建議
"""
import json
import re
from app.core.llm_router.router import chat_completion
from app.db import crud


class PromptOptimizer:

    async def analyze_and_suggest(self, project_id: str) -> dict:
        """分析負面回饋，產出優化建議"""
        # 1. 撈負面回饋
        feedbacks = crud.list_feedbacks_by_project(
            project_id, rating_filter=["partial", "wrong"], limit=20
        )
        if len(feedbacks) < 3:
            return {
                "status": "insufficient_data",
                "min_required": 3,
                "current_count": len(feedbacks),
            }

        # 2. 取當前 prompt
        active_prompt = crud.get_active_prompt(project_id)
        if not active_prompt:
            return {"status": "no_active_prompt"}

        # 3. 組合回饋上下文
        feedback_context = []
        for fb in feedbacks:
            entry = f"- Rating: {fb['rating']}"
            msg = fb.get("message")
            if msg:
                entry += f"\n  AI Response: {msg['content'][:200]}"
            if fb.get("correction_text"):
                entry += f"\n  User Correction: {fb['correction_text']}"
            feedback_context.append(entry)
        feedback_text = "\n\n".join(feedback_context)

        # 4. 呼叫 LLM 分析
        llm_messages = [
            {
                "role": "system",
                "content": (
                    "你是一位 Prompt 優化專家。分析以下使用者回饋和當前的 System Prompt，"
                    "找出需要改進的地方。\n\n"
                    "回傳 JSON 格式，結構如下：\n"
                    '{"changes": [\n'
                    '  {"type": "modify|add|remove", "section": "區段名稱", '
                    '"reason": "修改原因", "before": "修改前", "after": "修改後"}\n'
                    "]}\n\n"
                    "只回傳 JSON，不要其他文字。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## 當前 System Prompt\n\n{active_prompt['content']}\n\n"
                    f"## 使用者不滿意的回饋 ({len(feedbacks)} 筆)\n\n{feedback_text}"
                ),
            },
        ]

        llm_response = await chat_completion(messages=llm_messages)
        raw_output = llm_response.choices[0].message.content

        # 5. 解析 JSON
        changes = self._parse_changes(raw_output)

        # 6. 存建議
        suggestion = crud.create_suggestion(
            project_id=project_id,
            changes=changes,
            based_on_feedback_count=len(feedbacks),
        )

        return {"status": "generated", "suggestion": suggestion}

    async def apply_suggestion(self, project_id: str, suggestion_id: str) -> dict:
        """套用建議，產出新版 Prompt"""
        suggestion = crud.get_suggestion(suggestion_id)
        if not suggestion:
            return {"status": "error", "detail": "Suggestion not found"}
        if suggestion["status"] != "pending":
            return {"status": "error", "detail": f"Suggestion is {suggestion['status']}"}

        active_prompt = crud.get_active_prompt(project_id)
        if not active_prompt:
            return {"status": "error", "detail": "No active prompt"}

        # 格式化修改建議
        changes_text = json.dumps(suggestion["changes"], ensure_ascii=False, indent=2)

        # 用 LLM 合併
        llm_messages = [
            {
                "role": "system",
                "content": (
                    "你是一位 Prompt 工程專家。根據以下修改建議，更新 System Prompt。"
                    "保持格式和結構一致。只回傳更新後的完整 Prompt，不要其他說明。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## 當前 Prompt\n\n{active_prompt['content']}\n\n"
                    f"## 修改建議\n\n{changes_text}"
                ),
            },
        ]

        llm_response = await chat_completion(messages=llm_messages)
        new_content = llm_response.choices[0].message.content

        # 建立新版本
        version_num = crud.get_next_version_number(project_id)
        change_summary = ", ".join(
            c.get("section", "unknown") for c in suggestion["changes"]
        )
        new_version = crud.create_prompt_version(
            project_id=project_id,
            content=new_content,
            version=version_num,
            is_active=True,
            change_notes=f"Auto-optimized: {change_summary}",
        )

        # 更新建議狀態
        crud.update_suggestion_status(
            suggestion_id, "applied",
            result_prompt_version_id=new_version["id"],
        )

        return {"status": "applied", "new_version": new_version}

    async def reject_suggestion(self, suggestion_id: str) -> dict:
        """拒絕建議"""
        crud.update_suggestion_status(suggestion_id, "rejected")
        return {"status": "rejected"}

    def _parse_changes(self, raw: str) -> list[dict]:
        """解析 LLM 回傳的 JSON（容錯處理）"""
        # 先嘗試直接解析
        try:
            data = json.loads(raw)
            return data.get("changes", data if isinstance(data, list) else [])
        except json.JSONDecodeError:
            pass

        # 嘗試從 markdown code block 提取
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                return data.get("changes", data if isinstance(data, list) else [])
            except json.JSONDecodeError:
                pass

        # 回傳空
        return [{"type": "add", "section": "general", "reason": "LLM output parsing failed", "after": raw[:500]}]
