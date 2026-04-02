"""
Fine-tune Pipeline -- Extract training data from conversations
"""
import json
from app.db import crud


class FineTunePipeline:

    async def extract_training_data(self, project_id: str) -> list[dict]:
        """Extract high-quality training pairs from correct feedbacks"""
        pairs = crud.get_correct_feedbacks_with_context(project_id)
        return pairs

    async def export_jsonl(self, project_id: str, format: str = "openai") -> str:
        """Export training data as JSONL string"""
        pairs = await self.extract_training_data(project_id)
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
        feedback_stats = crud.get_feedback_stats(project_id)

        return {
            "total_training_pairs": len(pairs),
            "feedback_stats": feedback_stats,
            "ready_for_training": len(pairs) >= 10,
            "min_recommended": 50,
        }


finetune_pipeline = FineTunePipeline()
