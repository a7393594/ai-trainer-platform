"""
30 Knowledge Components (KC) seed — 撲克教練知識圖譜初始資料

Categories: preflop(8), postflop(10), tournament(5), mental(3), bankroll(2), advanced(2)
"""

CONCEPTS = [
    # ═══ Preflop (8) ═══
    {"code": "preflop_hand_rankings", "name": "起手牌強度排名", "category": "preflop",
     "bloom_level": "remember", "difficulty": 1,
     "description": "169 種起手牌的相對強度，從 AA 到 72o"},
    {"code": "preflop_position_ranges", "name": "位置開牌範圍", "category": "preflop",
     "bloom_level": "understand", "difficulty": 2,
     "prerequisite_codes": ["preflop_hand_rankings"],
     "description": "UTG 15-18%、CO 27-30%、BTN 43-48% 的 GTO 開牌範圍"},
    {"code": "preflop_open_sizing", "name": "開牌大小", "category": "preflop",
     "bloom_level": "apply", "difficulty": 2,
     "description": "標準 2.0-2.5bb open、SB 3bb、limp pot 策略"},
    {"code": "preflop_3bet", "name": "3-Bet 策略", "category": "preflop",
     "bloom_level": "apply", "difficulty": 3,
     "prerequisite_codes": ["preflop_position_ranges"],
     "description": "IP 6-9%、BB vs BTN 10-14% 的 3bet 範圍與 sizing"},
    {"code": "preflop_4bet_5bet", "name": "4-Bet / 5-Bet", "category": "preflop",
     "bloom_level": "analyze", "difficulty": 4,
     "prerequisite_codes": ["preflop_3bet"],
     "description": "4bet 6-9%、5bet QQ+/AK 的極化策略"},
    {"code": "preflop_squeeze", "name": "擠壓型 3-Bet", "category": "preflop",
     "bloom_level": "analyze", "difficulty": 4,
     "prerequisite_codes": ["preflop_3bet"],
     "description": "Squeeze 6-12%，多人底池的特殊 3bet 策略"},
    {"code": "preflop_bb_defense", "name": "大盲防守", "category": "preflop",
     "bloom_level": "apply", "difficulty": 3,
     "prerequisite_codes": ["preflop_position_ranges"],
     "description": "BB 面對不同位置 open 的 call/3bet 策略"},
    {"code": "preflop_short_stack", "name": "短籌碼推/棄", "category": "preflop",
     "bloom_level": "apply", "difficulty": 3,
     "description": "<15bb Nash push/fold 區間與 ICM 調整"},

    # ═══ Postflop (10) ═══
    {"code": "postflop_pot_odds", "name": "底池賠率", "category": "postflop",
     "bloom_level": "understand", "difficulty": 2,
     "description": "pot/(pot+bet) 計算、MDF、α 公式"},
    {"code": "postflop_cbet_flop", "name": "翻牌持續下注", "category": "postflop",
     "bloom_level": "apply", "difficulty": 3,
     "prerequisite_codes": ["postflop_pot_odds"],
     "description": "乾板 33% range-bet vs 濕板 66% 保護策略"},
    {"code": "postflop_cbet_turn", "name": "轉牌 Barrel", "category": "postflop",
     "bloom_level": "analyze", "difficulty": 4,
     "prerequisite_codes": ["postflop_cbet_flop"],
     "description": "三條件：range 優勢 + equity 轉移 + 充足 value"},
    {"code": "postflop_river_sizing", "name": "河牌 Sizing", "category": "postflop",
     "bloom_level": "analyze", "difficulty": 4,
     "prerequisite_codes": ["postflop_cbet_turn"],
     "description": "極化 sizing：75% / 125% / all-in 選擇"},
    {"code": "postflop_check_raise", "name": "Check-Raise 策略", "category": "postflop",
     "bloom_level": "analyze", "difficulty": 4,
     "prerequisite_codes": ["postflop_cbet_flop"],
     "description": "8-15% 頻率，nutted value + 半詐唬聽牌平衡"},
    {"code": "postflop_spr", "name": "SPR 分層決策", "category": "postflop",
     "bloom_level": "understand", "difficulty": 3,
     "description": "SPR 1-3 stack off / 4-6 兩街加注 / 7+ pot control"},
    {"code": "postflop_draw_play", "name": "聽牌打法", "category": "postflop",
     "bloom_level": "apply", "difficulty": 3,
     "prerequisite_codes": ["postflop_pot_odds"],
     "description": "Flush draw 9 outs + implied odds + semi-bluff"},
    {"code": "postflop_bluff_catch", "name": "抓詐唬", "category": "postflop",
     "bloom_level": "evaluate", "difficulty": 4,
     "prerequisite_codes": ["postflop_pot_odds", "postflop_river_sizing"],
     "description": "MDF 防守、blocker 分析、對手 range 解構"},
    {"code": "postflop_multiway", "name": "多人底池策略", "category": "postflop",
     "bloom_level": "apply", "difficulty": 3,
     "description": "多人底池大幅收緊 c-bet、重視 nutted hands"},
    {"code": "postflop_bet_fold_line", "name": "下注/棄牌路線", "category": "postflop",
     "bloom_level": "evaluate", "difficulty": 4,
     "description": "value bet 然後面對 raise 的決策邏輯"},

    # ═══ Tournament (5) ═══
    {"code": "mtt_icm_basics", "name": "ICM 基礎", "category": "tournament",
     "bloom_level": "understand", "difficulty": 3,
     "description": "非線性籌碼價值、covering stack 調整"},
    {"code": "mtt_bubble_play", "name": "泡沫期策略", "category": "tournament",
     "bloom_level": "apply", "difficulty": 4,
     "prerequisite_codes": ["mtt_icm_basics"],
     "description": "泡沫期 tight vs aggressive 根據籌碼深度"},
    {"code": "mtt_final_table", "name": "決賽桌策略", "category": "tournament",
     "bloom_level": "analyze", "difficulty": 5,
     "prerequisite_codes": ["mtt_icm_basics", "mtt_bubble_play"],
     "description": "最終桌 ICM 壓力、pay jumps 計算"},
    {"code": "mtt_push_fold", "name": "Push/Fold 區間", "category": "tournament",
     "bloom_level": "apply", "difficulty": 3,
     "prerequisite_codes": ["preflop_short_stack"],
     "description": "<15bb Nash 圖表、ante 調整"},
    {"code": "mtt_chip_ev_vs_dollar_ev", "name": "cEV vs $EV", "category": "tournament",
     "bloom_level": "evaluate", "difficulty": 5,
     "prerequisite_codes": ["mtt_icm_basics"],
     "description": "何時 chip EV 優先、何時 $EV 優先"},

    # ═══ Mental (3) ═══
    {"code": "mental_tilt_control", "name": "傾斜控制", "category": "mental",
     "bloom_level": "apply", "difficulty": 2,
     "description": "識別 tilt 觸發點、stop-loss 規則、呼吸法"},
    {"code": "mental_variance_understanding", "name": "方差理解", "category": "mental",
     "bloom_level": "understand", "difficulty": 2,
     "description": "10K 手以下 winrate 皆為雜訊、紅藍線分離"},
    {"code": "mental_session_discipline", "name": "Session 紀律", "category": "mental",
     "bloom_level": "apply", "difficulty": 2,
     "description": "開始/結束條件、疲勞管理、環境優化"},

    # ═══ Bankroll (2) ═══
    {"code": "bankroll_cash_management", "name": "Cash 資金管理", "category": "bankroll",
     "bloom_level": "understand", "difficulty": 2,
     "description": "NLHE 6-max 建議 20-50 buy-ins、升降級規則"},
    {"code": "bankroll_mtt_management", "name": "MTT 資金管理", "category": "bankroll",
     "bloom_level": "understand", "difficulty": 2,
     "description": "MTT 100-200 buy-ins、方差更高需更保守"},

    # ═══ Advanced (2) ═══
    {"code": "advanced_nodelock", "name": "Nodelock 剝削", "category": "advanced",
     "bloom_level": "create", "difficulty": 5,
     "prerequisite_codes": ["postflop_bluff_catch", "postflop_river_sizing"],
     "description": "在 solver 中鎖定對手偏差頻率，重新求解最大剝削策略"},
    {"code": "advanced_population_exploit", "name": "Population 剝削", "category": "advanced",
     "bloom_level": "create", "difficulty": 5,
     "prerequisite_codes": ["advanced_nodelock"],
     "description": "基於 population 統計的系統性偏離 GTO 策略"},
]


def seed_concepts(project_id: str):
    """Seed 30 KC to ait_concepts for a poker coach project."""
    from app.db.supabase import get_supabase
    sb = get_supabase()

    for c in CONCEPTS:
        data = {
            "project_id": project_id,
            "code": c["code"],
            "name": c["name"],
            "category": c["category"],
            "bloom_level": c.get("bloom_level", "remember"),
            "prerequisite_codes": c.get("prerequisite_codes", []),
            "description": c.get("description", ""),
            "difficulty": c.get("difficulty", 1),
        }
        # Upsert: skip if already exists
        existing = sb.table("ait_concepts").select("id").eq(
            "project_id", project_id
        ).eq("code", c["code"]).execute()
        if not existing.data:
            sb.table("ait_concepts").insert(data).execute()

    return len(CONCEPTS)
