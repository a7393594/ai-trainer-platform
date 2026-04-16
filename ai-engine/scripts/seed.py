"""
Seed 腳本 — 建立 demo 資料（冪等）

使用方式：
  cd ai-engine
  python -m scripts.seed
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase import init_supabase
from app.db import crud

DEMO_EMAIL = "demo@ai-trainer.dev"
DEMO_TENANT_NAME = "Demo Organization"
DEMO_PROJECT_NAME = "Poker AI Coach"
REFEREE_PROJECT_NAME = "Poker Referee AI"

INITIAL_PROMPT = """你是一位專業的撲克教練 AI，專門為撲克俱樂部提供策略指導和教學。

## 角色設定
- 你是一位經驗豐富的撲克教練，擅長德州撲克（NLH）和底池限注奧馬哈（PLO）
- 你的語氣友善但專業，像一位值得信賴的教練
- 你用繁體中文回答，術語可以中英混用

## 回答原則
1. 先理解玩家的具體情境（位置、持牌、牌面、對手特徵）
2. 給出清晰的建議，並解釋背後的邏輯
3. 適時引用 GTO（遊戲理論最優）概念，但也考慮實戰調整
4. 用具體的例子說明，避免過於抽象

## 你可以幫助的範圍
- 翻牌前/後策略分析
- 位置觀念和範圍分析
- 籌碼管理和資金規劃
- 錦標賽策略（ICM、泡沫期）
- 心態管理和傾斜控制
- 牌局覆盤和手牌分析

## 限制
- 不推薦任何線上賭博平台
- 不提供具體的金錢投資建議
- 不鼓勵過度遊戲或成癮行為
- 對未成年人相關問題保持警覺"""


def seed():
    init_supabase()

    # 檢查是否已有 demo user
    existing = crud.get_user_by_email(DEMO_EMAIL)
    if existing:
        print(f"✅ Demo 資料已存在:")
        print(f"   User ID:    {existing['id']}")
        print(f"   Tenant ID:  {existing['tenant_id']}")
        projects = crud.list_projects(existing["tenant_id"])
        for p in projects:
            print(f"   Project: {p['id']} ({p['name']}) type={p.get('project_type', 'unknown')}")

        # Backfill: 確保有 referee project
        has_referee = any(p.get("project_type") == "referee" for p in projects)
        if not has_referee:
            ref = crud.create_project(
                tenant_id=existing["tenant_id"],
                name=REFEREE_PROJECT_NAME,
                description="TDA 2024 裁判系統",
                domain_template="poker",
                project_type="referee",
            )
            print(f"✅ Backfill: Referee Project 建立: {ref['id']}")

        # Backfill: 現有 trainer projects 填充 domain_config
        from app.db.crud import DEFAULT_DOMAIN_CONFIGS, get_supabase
        for p in projects:
            if not p.get("domain_config") or p["domain_config"] == {}:
                ptype = p.get("project_type", "trainer")
                defaults = DEFAULT_DOMAIN_CONFIGS.get(ptype, {})
                get_supabase().table("ait_projects").update(
                    {"domain_config": defaults}
                ).eq("id", p["id"]).execute()
                print(f"   ↳ Backfilled domain_config for {p['name']}")

        return

    # 建立 tenant
    tenant = crud.create_tenant(DEMO_TENANT_NAME, plan="pro")
    print(f"✅ Tenant 建立: {tenant['id']} ({tenant['name']})")

    # 建立 user
    user = crud.create_user(
        tenant_id=tenant["id"],
        email=DEMO_EMAIL,
        role="admin",
        display_name="Demo Admin",
    )
    print(f"✅ User 建立: {user['id']} ({user['email']})")

    # 建立 trainer project
    project = crud.create_project(
        tenant_id=tenant["id"],
        name=DEMO_PROJECT_NAME,
        description="撲克 AI 教練訓練專案 — Demo",
        domain_template="poker",
        project_type="trainer",
    )
    print(f"✅ Trainer Project 建立: {project['id']} ({project['name']})")

    # 建立 referee project
    referee_project = crud.create_project(
        tenant_id=tenant["id"],
        name=REFEREE_PROJECT_NAME,
        description="TDA 2024 裁判系統",
        domain_template="poker",
        project_type="referee",
    )
    print(f"✅ Referee Project 建立: {referee_project['id']} ({referee_project['name']})")

    # 建立初始 prompt
    prompt = crud.create_prompt_version(
        project_id=project["id"],
        content=INITIAL_PROMPT,
        version=1,
        is_active=True,
        created_by=user["id"],
        change_notes="初始版本 — 由 seed 腳本建立",
    )
    print(f"✅ Prompt v1 建立: {prompt['id']} (is_active=True)")

    print("\n🎉 Seed 完成！")
    print(f"   Tenant ID:  {tenant['id']}")
    print(f"   User ID:    {user['id']}")
    print(f"   Project ID: {project['id']}")
    print(f"   Prompt ID:  {prompt['id']}")


if __name__ == "__main__":
    seed()
