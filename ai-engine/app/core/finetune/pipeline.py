"""
Fine-tune Pipeline — 抽取、清理、匯出訓練資料 & 管理任務

Provider 支援：
  - openai    : 上傳 JSONL → 建 fine-tuning job → 輪詢狀態 → 取得模型 ID
  - anthropic : Anthropic 尚未公開 fine-tune API，保留 stub，呼叫會回 not_available
  - local     : 僅建立本地 job 記錄（不呼叫外部）

DB 欄位對應：
  - result_model_id 在「running」期間用來存 provider 的 external job id (ft-xxx)
  - 完成後覆寫為 provider 回傳的 fine-tuned model id (ft:gpt-4o-mini:...)
  - error_message 用來存 provider 最後的錯誤訊息
"""
from __future__ import annotations

import io
import json

from app.config import settings
from app.db import crud


MIN_TRAINING_PAIRS = 10
RECOMMENDED_TRAINING_PAIRS = 50


class FineTunePipeline:

    # ----------------------------
    # 資料抽取 / 匯出
    # ----------------------------

    async def extract_training_data(self, project_id: str) -> list[dict]:
        return crud.get_correct_feedbacks_with_context(project_id)

    async def clean_training_data(self, pairs: list[dict]) -> list[dict]:
        seen = set()
        cleaned = []
        for pair in pairs:
            user_msg = (pair.get("user_message") or "").strip()
            asst_msg = (pair.get("assistant_message") or "").strip()
            if not user_msg or not asst_msg:
                continue
            if len(asst_msg) < 10 or len(asst_msg) > 10000:
                continue
            key = user_msg[:200].lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append({"user_message": user_msg, "assistant_message": asst_msg})
        return cleaned

    async def export_jsonl(self, project_id: str, format: str = "openai") -> str:
        pairs = await self.extract_training_data(project_id)
        pairs = await self.clean_training_data(pairs)
        prompt = crud.get_active_prompt(project_id)
        system_content = prompt["content"] if prompt else ""

        lines = []
        for pair in pairs:
            if format == "openai":
                entry = {
                    "messages": [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": pair["user_message"]},
                        {"role": "assistant", "content": pair["assistant_message"]},
                    ]
                }
            elif format == "anthropic":
                entry = {
                    "system": system_content,
                    "messages": [
                        {"role": "user", "content": pair["user_message"]},
                        {"role": "assistant", "content": pair["assistant_message"]},
                    ],
                }
            else:
                entry = {"input": pair["user_message"], "output": pair["assistant_message"]}
            lines.append(json.dumps(entry, ensure_ascii=False))

        return "\n".join(lines)

    async def get_stats(self, project_id: str) -> dict:
        pairs = await self.extract_training_data(project_id)
        cleaned = await self.clean_training_data(pairs)
        return {
            "total_raw_pairs": len(pairs),
            "total_clean_pairs": len(cleaned),
            "feedback_stats": crud.get_feedback_stats(project_id),
            "ready_for_training": len(cleaned) >= MIN_TRAINING_PAIRS,
            "min_recommended": RECOMMENDED_TRAINING_PAIRS,
        }

    # ----------------------------
    # Job 管理
    # ----------------------------

    async def create_job(self, project_id: str, provider: str, model_base: str) -> dict:
        """建立 fine-tune job 並（若可能）提交給 provider。"""
        pairs = await self.extract_training_data(project_id)
        cleaned = await self.clean_training_data(pairs)
        if len(cleaned) < MIN_TRAINING_PAIRS:
            return {
                "status": "error",
                "message": f"Not enough training data ({len(cleaned)} pairs, min {MIN_TRAINING_PAIRS})",
            }

        job = crud.create_finetune_job(project_id, provider, model_base, len(cleaned))
        jsonl = await self.export_jsonl(project_id, format=provider if provider in ("openai", "anthropic") else "openai")

        try:
            if provider == "openai":
                external = await self._submit_openai(model_base, jsonl)
                crud.update_finetune_job(job["id"], status="running", result_model_id=external["job_id"])
                return {
                    "status": "submitted",
                    "provider": "openai",
                    "job": {**job, "status": "running", "result_model_id": external["job_id"]},
                    "training_pairs": len(cleaned),
                    "external": external,
                }
            if provider == "anthropic":
                crud.update_finetune_job(
                    job["id"], status="failed",
                    error_message="Anthropic fine-tune API is not publicly available yet",
                )
                return {
                    "status": "not_available",
                    "provider": "anthropic",
                    "job": job,
                    "message": "Anthropic fine-tune API is not publicly available yet",
                }

            # local / unknown → 僅標記為 running，待外部流程回報
            crud.update_finetune_job(job["id"], status="running")
            return {
                "status": "created",
                "provider": provider,
                "job": {**job, "status": "running"},
                "training_pairs": len(cleaned),
            }
        except FineTuneSubmitError as e:
            crud.update_finetune_job(job["id"], status="failed", error_message=str(e))
            return {"status": "failed", "job": job, "error": str(e)}

    async def poll_job(self, job_id: str, auto_switch: bool = True) -> dict:
        """輪詢 provider 任務狀態，若完成則更新為 completed/failed。

        完成（succeeded）時：
          - result_model_id 覆寫為 provider 回傳的 fine-tuned model
          - 若 auto_switch=True（預設），把 project.default_model 設為新模型
        """
        job = crud.get_finetune_job(job_id)
        if not job:
            return {"status": "error", "message": "Job not found"}
        if job.get("status") in ("completed", "failed"):
            return {"status": job["status"], "job": job}

        provider = job.get("provider")
        external_id = job.get("result_model_id")  # 中間態：provider 的 job id
        if not external_id:
            return {"status": job.get("status", "running"), "job": job, "note": "no external id recorded"}

        try:
            if provider == "openai":
                info = await self._poll_openai(external_id)
                if info["status"] == "succeeded":
                    new_model = info.get("fine_tuned_model") or ""
                    crud.update_finetune_job(job_id, status="completed", result_model_id=new_model)
                    switched_from = None
                    if auto_switch and new_model:
                        project_id = job.get("project_id")
                        if project_id:
                            try:
                                project = crud.get_project(project_id)
                                switched_from = (project or {}).get("default_model")
                                crud.update_project_default_model(project_id, new_model)
                            except Exception as e:  # noqa: BLE001
                                print(f"[WARN] auto-switch default_model failed: {e}")
                    return {
                        "status": "succeeded",
                        "job": crud.get_finetune_job(job_id),
                        "external": info,
                        "auto_switched": bool(auto_switch and new_model),
                        "switched_from": switched_from,
                        "switched_to": new_model if auto_switch else None,
                    }
                if info["status"] == "failed":
                    crud.update_finetune_job(job_id, status="failed", error_message=info.get("error") or "failed")
                return {"status": info["status"], "job": crud.get_finetune_job(job_id), "external": info}
        except FineTuneSubmitError as e:
            crud.update_finetune_job(job_id, status="failed", error_message=str(e))
            return {"status": "failed", "error": str(e)}

        return {"status": job.get("status", "running"), "job": job}

    async def list_jobs(self, project_id: str) -> list[dict]:
        return crud.list_finetune_jobs(project_id)

    async def get_job(self, job_id: str) -> dict:
        job = crud.get_finetune_job(job_id)
        if not job:
            return {"status": "error", "message": "Job not found"}
        return job

    async def complete_job(self, job_id: str, result_model_id: str) -> dict:
        return crud.update_finetune_job(job_id, status="completed", result_model_id=result_model_id)

    async def fail_job(self, job_id: str, error_message: str) -> dict:
        return crud.update_finetune_job(job_id, status="failed", error_message=error_message)

    # ----------------------------
    # Provider 實接
    # ----------------------------

    async def _submit_openai(self, model_base: str, jsonl: str) -> dict:
        api_key = settings.openai_api_key
        if not api_key:
            raise FineTuneSubmitError("OPENAI_API_KEY not configured")
        try:
            from openai import AsyncOpenAI  # lazy import
        except ImportError as e:
            raise FineTuneSubmitError(f"openai package missing: {e}") from e

        client = AsyncOpenAI(api_key=api_key)
        try:
            file_obj = io.BytesIO(jsonl.encode("utf-8"))
            file_obj.name = "training.jsonl"
            file_resp = await client.files.create(file=file_obj, purpose="fine-tune")
            job_resp = await client.fine_tuning.jobs.create(
                training_file=file_resp.id,
                model=model_base,
            )
            return {
                "file_id": file_resp.id,
                "job_id": job_resp.id,
                "status": job_resp.status,
                "model": job_resp.model,
            }
        except Exception as e:  # noqa: BLE001
            raise FineTuneSubmitError(f"openai submit failed: {e}") from e

    async def _poll_openai(self, job_id: str) -> dict:
        api_key = settings.openai_api_key
        if not api_key:
            raise FineTuneSubmitError("OPENAI_API_KEY not configured")
        try:
            from openai import AsyncOpenAI  # lazy import
        except ImportError as e:
            raise FineTuneSubmitError(f"openai package missing: {e}") from e

        client = AsyncOpenAI(api_key=api_key)
        try:
            job = await client.fine_tuning.jobs.retrieve(job_id)
        except Exception as e:  # noqa: BLE001
            raise FineTuneSubmitError(f"openai poll failed: {e}") from e

        status_map = {
            "succeeded": "succeeded",
            "failed": "failed",
            "cancelled": "failed",
        }
        return {
            "status": status_map.get(job.status, "running"),
            "raw_status": job.status,
            "fine_tuned_model": getattr(job, "fine_tuned_model", None),
            "error": getattr(getattr(job, "error", None), "message", None),
        }


class FineTuneSubmitError(Exception):
    """Raised when a provider submit / poll call fails."""


finetune_pipeline = FineTunePipeline()
