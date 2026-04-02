"""
Domain Templates -- Onboarding 問題模板系統

每個模板定義一組引導式問題，用來建立 AI 的初始基線
"""

DOMAIN_TEMPLATES: dict[str, dict] = {
    "poker": {
        "id": "poker",
        "name": "Poker AI Coach",
        "description": "Training a poker coaching AI assistant",
        "questions": [
            {
                "id": "q1_game_types",
                "question": "你的俱樂部常玩哪些牌型？",
                "widget_type": "multi_select",
                "options": [
                    {"id": "nlh", "label": "NLH (No-Limit Hold'em)"},
                    {"id": "plo", "label": "PLO (Pot-Limit Omaha)"},
                    {"id": "mixed", "label": "混合賽"},
                    {"id": "tournament", "label": "錦標賽 (MTT)"},
                    {"id": "sng", "label": "SNG (Sit & Go)"},
                ],
                "required": True,
                "config": {},
            },
            {
                "id": "q2_skill_level",
                "question": "成員平均打牌程度大約是？",
                "widget_type": "single_select",
                "options": [
                    {"id": "beginner", "label": "新手", "description": "打牌經驗不到1年"},
                    {"id": "intermediate", "label": "有經驗", "description": "1-3年經驗"},
                    {"id": "advanced", "label": "老手", "description": "3年以上"},
                    {"id": "mixed", "label": "混合程度"},
                ],
                "required": True,
                "config": {},
            },
            {
                "id": "q3_blind_levels",
                "question": "常打的級別（盲注）？",
                "widget_type": "multi_select",
                "options": [
                    {"id": "micro", "label": "微注", "description": "1/2 以下"},
                    {"id": "low", "label": "低注", "description": "1/2 - 2/5"},
                    {"id": "mid", "label": "中注", "description": "5/10 - 10/20"},
                    {"id": "high", "label": "高注", "description": "25/50+"},
                ],
                "required": True,
                "config": {},
            },
            {
                "id": "q4_table_format",
                "question": "常見的桌型是？",
                "widget_type": "multi_select",
                "options": [
                    {"id": "6max", "label": "6人桌"},
                    {"id": "9max", "label": "9人桌"},
                    {"id": "heads_up", "label": "單挑 (Heads-Up)"},
                ],
                "required": True,
                "config": {},
            },
            {
                "id": "q5_common_topics",
                "question": "會員最常問的問題類型？",
                "widget_type": "multi_select",
                "options": [
                    {"id": "preflop", "label": "翻牌前策略"},
                    {"id": "postflop", "label": "翻牌後打法"},
                    {"id": "position", "label": "位置觀念"},
                    {"id": "bankroll", "label": "籌碼管理"},
                    {"id": "tournament", "label": "錦標賽策略"},
                    {"id": "mental", "label": "心態管理"},
                ],
                "required": True,
                "config": {},
            },
            {
                "id": "q6_tone",
                "question": "你希望 AI 教練的語氣風格？",
                "widget_type": "single_select",
                "options": [
                    {"id": "professional", "label": "專業嚴謹"},
                    {"id": "friendly", "label": "輕鬆友善"},
                    {"id": "coach", "label": "教練式", "description": "會挑戰你的思考"},
                    {"id": "casual", "label": "隨性自然"},
                ],
                "required": True,
                "config": {},
            },
            {
                "id": "q7_format",
                "question": "偏好的回答格式？",
                "widget_type": "single_select",
                "options": [
                    {"id": "concise", "label": "簡潔扼要", "description": "3-5 句重點"},
                    {"id": "detailed", "label": "詳細解說", "description": "含分析過程"},
                    {"id": "example", "label": "舉例為主", "description": "用實際牌局說明"},
                ],
                "required": True,
                "config": {},
            },
            {
                "id": "q8_restrictions",
                "question": "有什麼 AI 不該做的事嗎？",
                "widget_type": "form",
                "options": [],
                "required": False,
                "config": {
                    "fields": [
                        {
                            "name": "dont_do",
                            "label": "AI 不該做的事",
                            "type": "text",
                            "placeholder": "例如：不要推薦線上賭博平台",
                        }
                    ]
                },
            },
        ],
    },
    "general": {
        "id": "general",
        "name": "General AI Assistant",
        "description": "Training a general-purpose AI assistant",
        "questions": [
            {
                "id": "q1_purpose",
                "question": "你想讓 AI 做什麼？",
                "widget_type": "form",
                "options": [],
                "required": True,
                "config": {
                    "fields": [
                        {
                            "name": "purpose",
                            "label": "AI 的用途",
                            "type": "text",
                            "placeholder": "例如：回答客戶問題、提供技術支援",
                        }
                    ]
                },
            },
            {
                "id": "q2_audience",
                "question": "目標使用者是？",
                "widget_type": "single_select",
                "options": [
                    {"id": "technical", "label": "技術人員"},
                    {"id": "general", "label": "一般使用者"},
                    {"id": "mixed", "label": "混合"},
                ],
                "required": True,
                "config": {},
            },
            {
                "id": "q3_tone",
                "question": "回答的語氣風格？",
                "widget_type": "single_select",
                "options": [
                    {"id": "professional", "label": "專業"},
                    {"id": "casual", "label": "輕鬆"},
                    {"id": "friendly", "label": "友善"},
                    {"id": "coach", "label": "教練式"},
                ],
                "required": True,
                "config": {},
            },
            {
                "id": "q4_format",
                "question": "偏好的回答格式？",
                "widget_type": "single_select",
                "options": [
                    {"id": "concise", "label": "簡潔"},
                    {"id": "detailed", "label": "詳細"},
                    {"id": "step_by_step", "label": "步驟式"},
                ],
                "required": True,
                "config": {},
            },
            {
                "id": "q5_restrictions",
                "question": "AI 有什麼限制或不該做的事？",
                "widget_type": "form",
                "options": [],
                "required": False,
                "config": {
                    "fields": [
                        {
                            "name": "dont_do",
                            "label": "AI 不該做的事",
                            "type": "text",
                            "placeholder": "例如：不要給醫療建議",
                        }
                    ]
                },
            },
        ],
    },
}


def get_template(template_id: str) -> dict | None:
    return DOMAIN_TEMPLATES.get(template_id)


def list_templates() -> list[dict]:
    return [
        {"id": t["id"], "name": t["name"], "description": t["description"],
         "question_count": len(t["questions"])}
        for t in DOMAIN_TEMPLATES.values()
    ]
