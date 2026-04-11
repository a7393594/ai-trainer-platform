"""
Fine-tune Pipeline -- Extract, clean, export training data & manage jobs
"""
import json
from app.db import crud


class FineTunePipeline:

    async def extract_training_data(self, project_id: str) -> list[dict]:
        """Extract high-quality training pairs from correct feedbacks"""
        pairs = crud.get_correct_feedbacks_with_context(project_id)
        return pairs

    async def clean_training_data(self, pairs: list[dict]) -> list[dict]:
        """Clean and deduplicate training pairs"""
        seen = set()
        cleaned = []
        for pair in pairs:
            user_msg = pair.get("user_message", "").strip()
            asst_msg = pair.get("assistant_message", "").strip()
            if not user_msg or not asst_msg:
                continue
            # Skip very short or very long responses
            if len(asst_msg) < 10 or len(asst_msg) > 10000:
                continue
            # Deduplicate by user message
            key = user_msg[:200].lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append({"user_message": user_msg, "assistant_message": asst_msg})
        return cleaned

    async def export_jsonl(self, project_id: str, format: str = "openai") -> str:
        """Export training data as JSONL string"""
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
                    ]
                }
            else:
                entry = {
                    "input": pair["user_message"],
                    "output": pair["assistant_message"],
                }
            lines.append(json.dumps(entry, ensure_ascii=False))

        return "\n".join(lines)

    async def get_stats(self, project_id: str) -> dict:
        """Get fine-tune data statistics"""
        pairs = await self.extract_training_data(project_id)
        cleaned = await self.clean_training_data(pairs)
        feedback_stats = crud.get_feedback_stats(project_id)

        return {
            "total_raw_pairs": len(pairs),
            "total_clean_pairs": len(cleaned),
            "feedback_stats": feedback_stats,
            "ready_for_training": len(cleaned) >= 10,
            "min_recommended": 50,
        }

    async def create_job(self, project_id: str, provider: str, model_base: str) -> dict:
        """Create a fine-tune job record"""
        pairs = await self.extract_training_data(project_id)
        cleaned = await self.clean_training_data(pairs)
        if len(cleaned) < 10:
            return {"status": "error", "message": f"Not enough training data ({len(cleaned)} pairs, minimum 10)"}

        job = crud.create_finetune_job(project_id, provider, model_base, len(cleaned))
        # Mark as running (actual training would be async via provider API)
        crud.update_finetune_job(job["id"], status="running")
        return {"status": "created", "job": {**job, "status": "running"}, "training_pairs": len(cleaned)}

    async def list_jobs(self, project_id: str) -> list[dict]:
        """List all fine-tune jobs"""
        return crud.list_finetune_jobs(project_id)

    async def get_job(self, job_id: str) -> dict:
        """Get a fine-tune job"""
        job = crud.get_finetune_job(job_id)
        if not job:
            return {"status": "error", "message": "Job not found"}
        return job

    async def complete_job(self, job_id: str, result_model_id: str) -> dict:
        """Mark a job as completed with the resulting model ID"""
        return crud.update_finetune_job(job_id, status="completed", result_model_id=result_model_id)

    async def fail_job(self, job_id: str, error_message: str) -> dict:
        """Mark a job as failed"""
        return crud.update_finetune_job(job_id, status="failed", error_message=error_message)


finetune_pipeline = FineTunePipeline()
