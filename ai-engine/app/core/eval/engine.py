"""
Eval Engine -- Test case management and automated evaluation
"""
import json
from app.db import crud
from app.core.llm_router.router import chat_completion

# Regression detection thresholds
REGRESSION_THRESHOLD_PER_CASE = 15  # single case score drop
REGRESSION_THRESHOLD_OVERALL = 5    # overall avg score drop


class EvalEngine:

    async def run_eval(self, project_id: str, model: str = None) -> dict:
        """Run all test cases against current prompt"""
        test_cases = crud.list_test_cases(project_id)
        if not test_cases:
            return {"status": "no_test_cases", "message": "No test cases found"}

        prompt = crud.get_active_prompt(project_id)
        if not prompt:
            return {"status": "no_prompt", "message": "No active prompt"}

        model = model or "claude-sonnet-4-20250514"
        results = []
        total_score = 0
        passed = 0
        failed = 0

        for tc in test_cases:
            # Generate response
            messages = [
                {"role": "system", "content": prompt["content"]},
                {"role": "user", "content": tc["input_text"]},
            ]
            try:
                response = await chat_completion(messages=messages, model=model, max_tokens=1000)
                actual = response.choices[0].message.content
            except Exception as e:
                actual = f"[Error: {e}]"

            # Judge with LLM
            score, is_passed, reason = await self._judge(
                tc["input_text"], tc["expected_output"], actual
            )

            total_score += score
            if is_passed:
                passed += 1
            else:
                failed += 1

            results.append({
                "test_case_id": tc["id"],
                "input": tc["input_text"],
                "expected": tc["expected_output"],
                "actual": actual,
                "score": score,
                "passed": is_passed,
                "reason": reason,
            })

        avg_score = total_score / len(test_cases) if test_cases else 0

        # Save run
        run = crud.create_eval_run(
            project_id=project_id,
            prompt_version_id=prompt["id"],
            model_used=model,
            total_score=avg_score,
            passed_count=passed,
            failed_count=failed,
        )

        # Save individual results
        for r in results:
            crud.create_eval_result(
                run_id=run["id"],
                test_case_id=r["test_case_id"],
                actual_output=r["actual"],
                score=r["score"],
                passed=r["passed"],
                details={"reason": r["reason"]},
            )

        # Update prompt version eval_score
        try:
            crud.update_prompt_eval_score(prompt["id"], avg_score)
        except Exception:
            pass  # non-critical

        # Regression detection
        regression_data = crud.get_regression_comparison(project_id, run["id"])

        return {
            "status": "completed",
            "run_id": run["id"],
            "total_score": avg_score,
            "passed_count": passed,
            "failed_count": failed,
            "total_cases": len(test_cases),
            "results": results,
            "regression_detected": regression_data.get("regression_detected", False),
            "overall_delta": regression_data.get("overall_delta", 0),
            "regressions": regression_data.get("regressions", []),
        }

    async def _judge(self, input_text: str, expected: str, actual: str) -> tuple:
        """Use LLM to judge response quality"""
        try:
            judge_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an evaluation judge. Compare the actual AI response to the expected response.\n"
                        "Score from 0-100. A response is 'passed' if score >= 70.\n"
                        "Reply with JSON only: {\"score\": 85, \"passed\": true, \"reason\": \"brief explanation\"}"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Input: {input_text}\n\n"
                        f"Expected: {expected}\n\n"
                        f"Actual: {actual}"
                    ),
                },
            ]
            response = await chat_completion(
                messages=judge_messages,
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
            )
            raw = response.choices[0].message.content
            # Parse JSON
            data = json.loads(raw) if raw.startswith("{") else json.loads(
                raw[raw.index("{"):raw.rindex("}") + 1]
            )
            return data.get("score", 0), data.get("passed", False), data.get("reason", "")
        except Exception:
            return 50, False, "Judge failed"

    async def judge_quality(
        self,
        question: str,
        response: str,
        principles: str = "",
        judge_model: str = "claude-haiku-4-5-20251001",
    ) -> tuple[int, str, str]:
        """Pipeline Studio 用:沒有 expected 的情況下根據教學原則打分(0-100)。

        回傳 (score, reason, judge_model)。Fire-and-forget 失敗時回 (50, 'judge failed', ...)。
        """
        try:
            principles_section = principles.strip() or "（沒有額外原則,按通用 AI 教學回覆品質評估)"
            prompt = (
                "你是 AI 回覆品質評估器。根據以下標準給分(0-100):\n"
                "1. 準確性(30%):回答是否正確、不誤導\n"
                "2. 引導品質(25%):是否鼓勵使用者思考而非直接給答案\n"
                "3. 個人化(20%):是否考慮使用者背景\n"
                "4. 清晰度(15%):表達是否清楚易懂\n"
                "5. 完整性(10%):是否涵蓋關鍵資訊\n\n"
                f"使用者問題:\n{question}\n\n"
                f"教學原則:\n{principles_section}\n\n"
                f"AI 回覆:\n{response}\n\n"
                "只回傳 JSON,格式 {\"score\": 0-100, \"reason\": \"一句簡短說明\"}"
            )
            result = await chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=judge_model,
                max_tokens=200,
                temperature=0,
                span_label="judge_quality",
            )
            raw = (result.choices[0].message.content or "").strip()
            # 盡量從回覆裡撈出 JSON
            if raw.startswith("{"):
                data = json.loads(raw)
            else:
                start = raw.find("{")
                end = raw.rfind("}")
                if start >= 0 and end > start:
                    data = json.loads(raw[start : end + 1])
                else:
                    return 50, "judge output not JSON", judge_model
            score = int(data.get("score", 50))
            score = max(0, min(100, score))
            reason = str(data.get("reason", ""))[:500]
            return score, reason, judge_model
        except Exception as e:
            return 50, f"judge failed: {e}", judge_model


    async def ai_review_run(
        self,
        run_id: str,
        judge_model: str = "claude-opus-4-20250514",
    ) -> dict:
        """用強模型對既有 eval_run 的每筆結果重新打分，寫回 eval_results。

        - 不改動原始 actual_output，僅更新 score/passed/details.ai_review
        - 回傳 {run_id, reviewed, updated_score, deltas}
        """
        run = crud.get_eval_run(run_id) if hasattr(crud, "get_eval_run") else None
        results = crud.get_eval_run_details(run_id)
        if not results:
            return {"status": "no_results", "run_id": run_id}

        items = results.get("results") if isinstance(results, dict) else results
        if not items:
            return {"status": "no_results", "run_id": run_id}

        reviewed = 0
        new_total = 0.0
        passed_cnt = 0
        deltas: list[dict] = []
        for r in items:
            tc = r.get("test_case") or {}
            input_text = tc.get("input_text") or r.get("input") or ""
            expected = tc.get("expected_output") or r.get("expected") or ""
            actual = r.get("actual_output") or r.get("actual") or ""
            try:
                score, is_passed, reason = await self._judge_with_model(
                    input_text, expected, actual, judge_model
                )
            except Exception as e:  # noqa: BLE001
                score, is_passed, reason = r.get("score", 0), r.get("passed", False), f"judge failed: {e}"

            prev_score = r.get("score") or 0
            deltas.append({"result_id": r.get("id"), "prev": prev_score, "new": score})
            new_total += score
            if is_passed:
                passed_cnt += 1

            details = r.get("details") or {}
            details["ai_review"] = {
                "judge_model": judge_model,
                "score": score,
                "passed": is_passed,
                "reason": reason,
                "prev_score": prev_score,
            }
            try:
                if hasattr(crud, "update_eval_result"):
                    crud.update_eval_result(
                        result_id=r.get("id"),
                        score=score,
                        passed=is_passed,
                        details=details,
                    )
                reviewed += 1
            except Exception:
                pass

        avg = new_total / len(items) if items else 0
        try:
            if hasattr(crud, "update_eval_run_scores"):
                crud.update_eval_run_scores(
                    run_id=run_id,
                    total_score=avg,
                    passed_count=passed_cnt,
                    failed_count=len(items) - passed_cnt,
                )
        except Exception:
            pass

        return {
            "status": "completed",
            "run_id": run_id,
            "reviewed": reviewed,
            "judge_model": judge_model,
            "updated_score": avg,
            "passed_count": passed_cnt,
            "failed_count": len(items) - passed_cnt,
            "deltas": deltas,
        }

    async def _judge_with_model(
        self, input_text: str, expected: str, actual: str, model: str
    ) -> tuple[int, bool, str]:
        try:
            resp = await chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict evaluation judge. Compare actual vs expected.\n"
                            "Score 0-100. Pass ≥ 70.\n"
                            "Reply JSON only: {\"score\":85,\"passed\":true,\"reason\":\"...\"}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Input: {input_text}\n\nExpected: {expected}\n\nActual: {actual}",
                    },
                ],
                model=model,
                max_tokens=250,
                temperature=0,
            )
            raw = (resp.choices[0].message.content or "").strip()
            s = raw.find("{")
            e = raw.rfind("}")
            data = json.loads(raw[s : e + 1]) if s >= 0 and e > s else {}
            score = int(data.get("score", 0))
            passed = bool(data.get("passed", score >= 70))
            return max(0, min(100, score)), passed, str(data.get("reason", ""))[:500]
        except Exception as e:  # noqa: BLE001
            return 50, False, f"judge failed: {e}"

    async def cluster_gaps(
        self,
        run_id: str,
        max_clusters: int = 6,
        judge_model: str = "claude-sonnet-4-20250514",
    ) -> dict:
        """將 run 中失敗的測試案例用 LLM 聚類為弱點類別。

        回傳：
          {
            "run_id": ...,
            "failure_count": N,
            "clusters": [
              {"name": "...", "description": "...", "test_case_ids": [...], "suggestion": "..."}
            ]
          }
        """
        details = crud.get_eval_run_details(run_id)
        items = details.get("results", []) if isinstance(details, dict) else details
        failed = [r for r in (items or []) if not r.get("passed")]
        if not failed:
            return {"run_id": run_id, "failure_count": 0, "clusters": []}

        # 準備聚類輸入
        lines = []
        for r in failed[:40]:  # 控制 token；取前 40 筆
            tc = r.get("test_case") or {}
            inp = (tc.get("input_text") or r.get("input") or "")[:220]
            exp = (tc.get("expected_output") or r.get("expected") or "")[:180]
            act = (r.get("actual_output") or "")[:180]
            lines.append(
                f"- id={r.get('id')} | category={tc.get('category') or 'n/a'}\n"
                f"  input: {inp}\n  expected: {exp}\n  actual: {act}"
            )

        sys_prompt = (
            "你是 AI 測試失敗分析師。請把下列失敗案例聚類成最多 "
            f"{max_clusters} 組弱點類別。回傳純 JSON：\n"
            "{ \"clusters\": [ {\"name\": \"類別名\", \"description\": \"一句話說明共通失因\", "
            "\"test_case_ids\": [\"id1\",\"id2\"], \"suggestion\": \"補救建議（Prompt/RAG/Eval 三選一）\"} ] }"
        )
        user = "失敗案例列表：\n" + "\n".join(lines)

        try:
            resp = await chat_completion(
                messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
                model=judge_model,
                max_tokens=1500,
                temperature=0.2,
            )
            raw = (resp.choices[0].message.content or "").strip()
            s = raw.find("{")
            e = raw.rfind("}")
            data = json.loads(raw[s : e + 1]) if s >= 0 and e > s else {}
            clusters = data.get("clusters", []) if isinstance(data, dict) else []
        except Exception as e:  # noqa: BLE001
            return {"run_id": run_id, "failure_count": len(failed), "clusters": [], "error": str(e)}

        return {
            "run_id": run_id,
            "failure_count": len(failed),
            "analyzed": min(len(failed), 40),
            "judge_model": judge_model,
            "clusters": clusters,
        }

    def compare_runs(self, project_id: str, run_id: str) -> dict:
        """Compare a run with its predecessor, with threshold-based regression detection"""
        data = crud.get_regression_comparison(project_id, run_id)
        # Apply stricter threshold labeling
        severe_regressions = [r for r in data.get("regressions", []) if r["delta"] < -REGRESSION_THRESHOLD_PER_CASE]
        data["severe_regressions"] = severe_regressions
        data["regression_level"] = (
            "critical" if data.get("overall_delta", 0) < -REGRESSION_THRESHOLD_OVERALL and severe_regressions
            else "warning" if data.get("regression_detected", False)
            else "ok"
        )
        return data


eval_engine = EvalEngine()
