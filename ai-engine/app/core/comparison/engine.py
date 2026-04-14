"""
Multi-Model Comparison Engine — 多模型知識蒸餾

核心流程：
1. 建立比較（選問題 + 選模型）
2. 批次執行（N 問題 × M 模型）
3. 投票/評審
4. 選定模型 + 概念差分析
5. 自動補齊（RAG / Prompt / Eval）
"""
import asyncio
import json
import time
from typing import Optional
from app.core.llm_router.router import chat_completion
from app.db import crud
from app.db.supabase import get_supabase

T_RUNS = "ait_comparison_runs"
T_RESPONSES = "ait_comparison_responses"
T_GAPS = "ait_concept_gaps"

# Model pricing (per 1M tokens, input/output)
MODEL_PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gemini/gemini-2.0-flash": {"input": 0.075, "output": 0.3},
}


GENERATE_QUESTIONS_PROMPT = """Based on the following AI system prompt, generate {count} key test questions that thoroughly cover the AI's domain knowledge.

Requirements:
- Questions should range from basic to advanced
- Cover different aspects of the domain
- Include both factual and analytical questions
- Be specific enough to have clear right/wrong answers
- Output as a JSON array: [{"id": "q1", "text": "question text"}, ...]
- Reply with ONLY the JSON array, no markdown code blocks"""

AUTO_JUDGE_PROMPT = """You are evaluating AI responses for correctness. For each response, judge if it is correct, partially correct, or incorrect.

Score each response:
- "correct": factually accurate, complete, helpful
- "partial": mostly correct but missing key details or has minor errors
- "incorrect": factually wrong, misleading, or unhelpful

Reply with a JSON array: [{"response_id": "...", "verdict": "correct|partial|incorrect", "reason": "brief explanation"}]
Reply with ONLY the JSON array."""


class ComparisonEngine:

    def create_run(self, project_id: str, name: str, questions: list[dict], models: list[str]) -> dict:
        """建立比較執行"""
        return get_supabase().table(T_RUNS).insert({
            "project_id": project_id,
            "name": name,
            "questions": questions,
            "models": models,
            "status": "pending",
        }).execute().data[0]

    def get_run(self, run_id: str) -> Optional[dict]:
        result = get_supabase().table(T_RUNS).select("*").eq("id", run_id).execute()
        return result.data[0] if result.data else None

    def list_runs(self, project_id: str) -> list[dict]:
        return get_supabase().table(T_RUNS).select("*").eq("project_id", project_id).order("created_at", desc=True).execute().data

    async def execute_run(self, run_id: str) -> dict:
        """批次執行：每個問題 × 每個模型"""
        run = self.get_run(run_id)
        if not run:
            return {"error": "Run not found"}

        questions = run.get("questions", [])
        models = run.get("models", [])
        project_id = run["project_id"]

        # Update status
        get_supabase().table(T_RUNS).update({"status": "running"}).eq("id", run_id).execute()

        # Load system prompt
        prompt = crud.get_active_prompt(project_id)
        system_content = prompt["content"] if prompt else ""

        total = len(questions) * len(models)
        completed = 0
        responses = []

        for q in questions:
            q_id = q.get("id", str(questions.index(q)))
            q_text = q.get("text", "")

            for model in models:
                start_time = time.time()
                try:
                    messages = [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": q_text},
                    ]
                    llm_resp = await chat_completion(messages=messages, model=model, max_tokens=2000)
                    response_text = llm_resp.choices[0].message.content or ""

                    # Token usage
                    usage = getattr(llm_resp, 'usage', None)
                    input_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
                    output_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0

                    # Cost calculation
                    pricing = MODEL_PRICING.get(model, {"input": 0, "output": 0})
                    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

                except Exception as e:
                    response_text = f"[Error: {e}]"
                    input_tokens = 0
                    output_tokens = 0
                    cost = 0

                latency = int((time.time() - start_time) * 1000)

                resp = get_supabase().table(T_RESPONSES).insert({
                    "run_id": run_id,
                    "question_id": q_id,
                    "model_id": model,
                    "response_text": response_text,
                    "latency_ms": latency,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": round(cost, 6),
                }).execute().data[0]

                responses.append(resp)
                completed += 1

        # Update status
        get_supabase().table(T_RUNS).update({"status": "completed"}).eq("id", run_id).execute()

        return {"status": "completed", "total": total, "completed": completed}

    def get_run_results(self, run_id: str) -> dict:
        """取得比較結果"""
        run = self.get_run(run_id)
        if not run:
            return {"error": "Run not found"}

        responses = get_supabase().table(T_RESPONSES).select("*").eq("run_id", run_id).execute().data

        # Group by question
        by_question: dict[str, list] = {}
        for r in responses:
            by_question.setdefault(r["question_id"], []).append(r)

        # Calculate per-model stats
        model_stats: dict[str, dict] = {}
        for r in responses:
            m = r["model_id"]
            if m not in model_stats:
                model_stats[m] = {"correct": 0, "partial": 0, "wrong": 0, "total": 0, "total_cost": 0, "total_latency": 0}
            model_stats[m]["total"] += 1
            model_stats[m]["total_cost"] += r.get("cost_usd", 0) or 0
            model_stats[m]["total_latency"] += r.get("latency_ms", 0) or 0
            if r.get("is_correct") is True:
                model_stats[m]["correct"] += 1
            elif r.get("is_correct") is False:
                model_stats[m]["wrong"] += 1

        for m, s in model_stats.items():
            s["accuracy"] = round(s["correct"] / s["total"] * 100, 1) if s["total"] > 0 else 0
            s["avg_cost"] = round(s["total_cost"] / s["total"], 6) if s["total"] > 0 else 0
            s["avg_latency"] = round(s["total_latency"] / s["total"]) if s["total"] > 0 else 0

        return {"run": run, "responses": by_question, "model_stats": model_stats}

    def vote(self, response_id: str, is_correct: Optional[bool] = None, voted_rank: Optional[int] = None) -> dict:
        """投票/標記正確性"""
        update: dict = {}
        if is_correct is not None:
            update["is_correct"] = is_correct
        if voted_rank is not None:
            update["voted_rank"] = voted_rank
        result = get_supabase().table(T_RESPONSES).update(update).eq("id", response_id).execute()
        return result.data[0] if result.data else {}

    def select_model(self, run_id: str, model_id: str) -> dict:
        """選定模型"""
        get_supabase().table(T_RUNS).update({"selected_model": model_id}).eq("id", run_id).execute()
        return {"status": "selected", "model": model_id}

    def analyze_gaps(self, run_id: str) -> list[dict]:
        """概念差分析：找出選定模型答錯但其他模型答對的問題"""
        run = self.get_run(run_id)
        if not run or not run.get("selected_model"):
            return []

        selected = run["selected_model"]
        project_id = run["project_id"]
        questions = run.get("questions", [])
        responses = get_supabase().table(T_RESPONSES).select("*").eq("run_id", run_id).execute().data

        # Group by question
        by_q: dict[str, dict[str, dict]] = {}
        for r in responses:
            by_q.setdefault(r["question_id"], {})[r["model_id"]] = r

        gaps = []
        for q in questions:
            q_id = q.get("id", str(questions.index(q)))
            q_text = q.get("text", "")
            q_responses = by_q.get(q_id, {})

            selected_resp = q_responses.get(selected)
            if not selected_resp or selected_resp.get("is_correct") is not False:
                continue  # Selected model got it right or hasn't been marked

            # Find a correct model
            correct_model = None
            correct_response = None
            for model_id, resp in q_responses.items():
                if model_id != selected and resp.get("is_correct") is True:
                    correct_model = model_id
                    correct_response = resp["response_text"]
                    break

            if not correct_model:
                continue  # No other model got it right either

            gap = get_supabase().table(T_GAPS).insert({
                "run_id": run_id,
                "project_id": project_id,
                "selected_model": selected,
                "question_id": q_id,
                "question_text": q_text,
                "selected_model_response": selected_resp["response_text"],
                "correct_response": correct_response,
                "correct_model": correct_model,
            }).execute().data[0]
            gaps.append(gap)

        return gaps

    def list_gaps(self, project_id: str) -> list[dict]:
        return get_supabase().table(T_GAPS).select("*").eq("project_id", project_id).order("created_at", desc=True).execute().data

    async def remediate_gap(self, gap_id: str, remediation_type: str) -> dict:
        """補齊概念差"""
        gap_data = get_supabase().table(T_GAPS).select("*").eq("id", gap_id).execute().data
        if not gap_data:
            return {"error": "Gap not found"}
        gap = gap_data[0]
        project_id = gap["project_id"]

        if remediation_type == "rag":
            # Add correct response to knowledge base
            doc = crud.create_knowledge_doc(
                project_id=project_id,
                title=f"[Auto] {gap['question_text'][:50]}",
                source_type="auto_extract",
                content=f"問題：{gap['question_text']}\n\n正確回答：{gap['correct_response']}",
            )
            # Chunk it
            from app.core.rag.pipeline import rag_pipeline
            await rag_pipeline.process_document(doc["id"])

        elif remediation_type == "eval":
            # Add as eval test case
            crud.create_test_case(
                project_id=project_id,
                input_text=gap["question_text"],
                expected_output=gap["correct_response"],
                category="concept_gap",
            )

        elif remediation_type == "prompt":
            # Create prompt suggestion
            prompt = crud.get_active_prompt(project_id)
            if prompt:
                crud.create_suggestion(
                    project_id=project_id,
                    prompt_version_id=prompt["id"],
                    suggested_changes={
                        "type": "concept_gap_fix",
                        "question": gap["question_text"],
                        "gap": f"模型在此問題答錯。正確答案應涵蓋：{gap['correct_response'][:200]}",
                    },
                    reasoning=f"概念差補齊：{gap['question_text'][:100]}",
                )

        # Update status
        get_supabase().table(T_GAPS).update({
            "remediation_type": remediation_type,
            "remediation_status": "applied",
        }).eq("id", gap_id).execute()

        return {"status": "applied", "type": remediation_type}


    async def generate_questions(self, project_id: str, count: int = 15) -> list[dict]:
        """AI 自動產出關鍵測試問題"""
        prompt = crud.get_active_prompt(project_id)
        system_content = prompt["content"] if prompt else "General AI assistant"

        messages = [
            {"role": "system", "content": GENERATE_QUESTIONS_PROMPT.format(count=count)},
            {"role": "user", "content": f"AI System Prompt:\n\n{system_content}"},
        ]

        response = await chat_completion(messages=messages, model="claude-sonnet-4-20250514", max_tokens=2000, project_id=project_id)
        raw = response.choices[0].message.content or "[]"

        # Parse JSON
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            questions = json.loads(cleaned)
            if isinstance(questions, list):
                return questions
        except (json.JSONDecodeError, IndexError):
            pass

        return [{"id": f"q{i}", "text": line.strip()} for i, line in enumerate(raw.split("\n")) if line.strip()]

    async def auto_judge(self, run_id: str) -> list[dict]:
        """AI 輔助評審 — 用最強模型自動打分"""
        run = self.get_run(run_id)
        if not run:
            return []

        questions = run.get("questions", [])
        responses = get_supabase().table(T_RESPONSES).select("*").eq("run_id", run_id).execute().data

        # Group by question
        by_q: dict[str, list] = {}
        for r in responses:
            by_q.setdefault(r["question_id"], []).append(r)

        all_verdicts = []

        for q in questions:
            q_id = q.get("id", str(questions.index(q)))
            q_text = q.get("text", "")
            q_responses = by_q.get(q_id, [])
            if not q_responses:
                continue

            # Build judge prompt
            resp_texts = "\n\n".join([
                f"[{r['id']}] Model: {r['model_id']}\nResponse: {r['response_text'][:500]}"
                for r in q_responses
            ])

            messages = [
                {"role": "system", "content": AUTO_JUDGE_PROMPT},
                {"role": "user", "content": f"Question: {q_text}\n\nResponses:\n{resp_texts}"},
            ]

            try:
                judge_resp = await chat_completion(messages=messages, model="claude-sonnet-4-20250514", max_tokens=1000)
                raw = judge_resp.choices[0].message.content or "[]"
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
                verdicts = json.loads(cleaned)

                for v in verdicts:
                    rid = v.get("response_id", "")
                    verdict = v.get("verdict", "")
                    is_correct = True if verdict == "correct" else (None if verdict == "partial" else False)

                    # Update in DB
                    if rid:
                        get_supabase().table(T_RESPONSES).update({"is_correct": is_correct}).eq("id", rid).execute()
                        all_verdicts.append({"response_id": rid, "verdict": verdict, "reason": v.get("reason", "")})
            except Exception:
                pass

        return all_verdicts

    def recommend_model(self, run_id: str) -> dict:
        """自動推薦模型 — 綜合 正確率 × 成本 × 延遲"""
        results = self.get_run_results(run_id)
        if "error" in results:
            return {"error": "Run not found"}

        stats = results.get("model_stats", {})
        if not stats:
            return {"recommendation": None, "reason": "No data"}

        # Scoring: accuracy (0.6) + cost_efficiency (0.25) + speed (0.15)
        scores = {}
        max_cost = max((s.get("avg_cost", 0) for s in stats.values()), default=0.001) or 0.001
        max_latency = max((s.get("avg_latency", 0) for s in stats.values()), default=1) or 1

        for model, s in stats.items():
            accuracy_score = (s.get("accuracy", 0) / 100) * 0.6
            cost_score = (1 - s.get("avg_cost", 0) / max_cost) * 0.25  # lower cost = higher score
            speed_score = (1 - s.get("avg_latency", 0) / max_latency) * 0.15  # lower latency = higher score
            total = accuracy_score + cost_score + speed_score
            scores[model] = {"total_score": round(total, 3), "accuracy": s.get("accuracy", 0), "cost": s.get("avg_cost", 0), "latency": s.get("avg_latency", 0)}

        best = max(scores.items(), key=lambda x: x[1]["total_score"])
        return {
            "recommendation": best[0],
            "score": best[1]["total_score"],
            "details": best[1],
            "all_scores": scores,
        }


comparison_engine = ComparisonEngine()
