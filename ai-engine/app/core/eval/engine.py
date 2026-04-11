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
