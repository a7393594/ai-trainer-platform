"""One-off seed：為每個 project 建立 prompt library 預設 slot 資料。

用法：
  cd ai-engine
  venv/Scripts/python.exe scripts/seed_prompt_library.py

Seed 內容：
  - analyze_intent：從 dag_executor.handle_analyze_intent 的 default_sys 搬過來
  - mode_coach / mode_research / mode_course / mode_battle：從 mode_prompts.MODE_PROMPTS 搬

若某 project 的某 slot 已有資料，跳過（不覆蓋）。
若某 project 已有 base slot（slot 'base' 或原本無 slot 的舊資料），保留不動。
"""
import os
import sys

# Setup env + path
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

env = {}
with open(os.path.join(ROOT, ".env"), encoding="utf-8") as f:
    for line in f:
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v
            os.environ.setdefault(k, v)

from supabase import create_client
from app.core.pipeline.mode_prompts import MODE_PROMPTS

sb = create_client(env["SUPABASE_URL"], env["SUPABASE_SERVICE_KEY"])

# analyze_intent 的預設 prompt — 和 dag_executor.handle_analyze_intent 的 default_sys 同步
AVAILABLE_MODES_DESC = ", ".join(
    f"{k}（{v['label']}：{v['description']}）" for k, v in MODE_PROMPTS.items()
)
ANALYZE_INTENT_PROMPT = f"""你是一個問題分析器。任務：把使用者問題拆成結構化 JSON，讓下游系統知道該做什麼。

可用的回覆人格（response_styles 的選項，可多選混用）：
{AVAILABLE_MODES_DESC}

分析四個維度：
1. actions           — 需要執行哪些動作（例：["計算 AA vs KK 勝率", "教 pot odds 概念", "出一題 BTN vs BB 翻前題"]）
2. warnings          — 本題使用者可能忽略或誤解的地方（例：["未說明籌碼深度", "可能混淆 equity 和 pot odds"]）
3. knowledge_points  — 相關知識關鍵字，給 RAG 定向檢索（例：["pot odds", "range balance", "c-bet sizing"]）
4. response_styles   — 該用哪些人格，用 key 名稱（coach/research/course/battle）。允許多選，例：["coach", "research"] 代表分析＋研究並重

輸出**純 JSON**（不要 markdown code block、不要加說明），格式：
{{
  "actions":          ["...", "..."],
  "warnings":         ["...", "..."],
  "knowledge_points": ["...", "..."],
  "response_styles":  ["coach"]
}}"""


SLOTS = [
    {
        "slot": "analyze_intent",
        "title": "中間層問題分析",
        "description": "用便宜模型把使用者問題拆成 actions + warnings + knowledge_points + response_styles（供下游節點取用）",
        "icon": "🧠",
        "category": "system",
        "content": ANALYZE_INTENT_PROMPT,
    },
    *[
        {
            "slot": f"mode_{mode_id}",
            "title": meta["label"] + "人格",
            "description": meta["description"],
            "icon": meta["icon"],
            "category": "persona",
            "content": meta["prompt"],
        }
        for mode_id, meta in MODE_PROMPTS.items()
    ],
]


def seed_for_project(project_id: str, project_name: str):
    print(f"\n=== {project_name} ({project_id}) ===")
    # 原本 ait_prompt_versions 的舊資料 slot 應該是預設 'base'（migration 的 DEFAULT）；
    # 但若 null 欄位尚未 backfill 完全，補一個 UPDATE 確保 base slot 正確
    sb.table("ait_prompt_versions").update({"slot": "base"}).eq("project_id", project_id).is_("slot", "null").execute()

    # 補 base slot 的 title/description 如缺
    active_base = (
        sb.table("ait_prompt_versions")
        .select("id,title")
        .eq("project_id", project_id)
        .eq("slot", "base")
        .eq("is_active", True)
        .execute()
    )
    if active_base.data and not active_base.data[0].get("title"):
        sb.table("ait_prompt_versions").update({
            "title": "主提示詞",
            "description": "compose_prompt 階段注入的主系統提示詞",
            "icon": "📝",
            "category": "system",
        }).eq("id", active_base.data[0]["id"]).execute()
        print("  ✓ backfilled base slot metadata")

    # Seed 每個 slot
    for slot_def in SLOTS:
        slot = slot_def["slot"]
        existing = (
            sb.table("ait_prompt_versions")
            .select("id,version")
            .eq("project_id", project_id)
            .eq("slot", slot)
            .execute()
        )
        if existing.data:
            print(f"  — {slot}: already has {len(existing.data)} version(s), skip")
            continue

        new_row = {
            "project_id": project_id,
            "slot": slot,
            "content": slot_def["content"],
            "version": 1,
            "is_active": True,
            "change_notes": "seed from code defaults",
            "title": slot_def["title"],
            "description": slot_def["description"],
            "icon": slot_def["icon"],
            "category": slot_def["category"],
        }
        sb.table("ait_prompt_versions").insert(new_row).execute()
        print(f"  ✓ inserted {slot} v1 ({slot_def['icon']} {slot_def['title']})")


def main():
    projects = sb.table("ait_projects").select("id,name").execute()
    print(f"Seeding {len(projects.data)} project(s)")
    for p in projects.data:
        seed_for_project(p["id"], p["name"])
    print("\nDone.")


if __name__ == "__main__":
    main()
