/**
 * Chat Modes — 4 種對話場景配置
 *
 * 每個 mode 定義：
 *   - label: UI 分頁名稱
 *   - icon: emoji
 *   - headerTitle: 主題（顯示在 chat 頁面 header）
 *   - headerSubtitle: 副標描述
 *   - systemPrompt: 詞根（system prompt 前綴，會在 compose_prompt 階段 prepend）
 *   - suggestions: 預設問題（chip 點擊即填入輸入框）
 */

export type ChatModeId = 'coach' | 'research' | 'course' | 'battle'

export interface ChatModeConfig {
  id: ChatModeId
  label: string
  icon: string
  headerTitle: string
  headerSubtitle: string
  systemPrompt: string
  suggestions: string[]
}

export const CHAT_MODES: Record<ChatModeId, ChatModeConfig> = {
  coach: {
    id: 'coach',
    label: '教練模式',
    icon: '🎯',
    headerTitle: '撲克教練',
    headerSubtitle: '分析你的打法、給出策略建議',
    systemPrompt: `你是一位資深撲克教練，風格嚴謹、具體、直指問題核心。

你的任務：
1. 根據使用者描述的牌局或決策，分析**對錯與原因**，不要模稜兩可。
2. 遇到勝率、EV、pot odds 計算時，**必定呼叫對應工具**取真實數據，不要憑記憶答。
3. 回答結構：① 結論（該怎麼打）② 原因（為什麼）③ 例外情境（什麼時候改變）。
4. 若使用者的理解有誤，直接指出並解釋正確觀念，不要敷衍。
5. 避免籠統的詞語（例如「要看情況」），每個建議都要可執行。`,
    suggestions: [
      '我在 BTN 拿 AKs，CO 3bet 我該 call 還是 4bet？',
      'K72 rainbow flop 我拿 AK 面對 check，該 c-bet 多少尺寸？',
      'AA 翻前對上各種對子的勝率是多少？',
      'SB vs BB 位置戰，我該怎麼構建 3bet range？',
    ],
  },
  research: {
    id: 'research',
    label: '研究助理',
    icon: '🔬',
    headerTitle: '撲克研究助理',
    headerSubtitle: '深度探討理論、比對數據、整理論點',
    systemPrompt: `你是一位撲克研究助理，擅長用數據支持論點、做多情境比較、整理成清楚的結論。

你的任務：
1. 面對理論問題（GTO、range、equity、EV），**用工具跑實際數字**，而不是用大概的百分比。
2. 多情境比較時，**一次規劃多個工具呼叫**（平行），最後做統整。
3. 回答結構：① 分析方法 ② 數據表格 ③ 關鍵發現 ④ 實戰意涵。
4. 引用假設（如籌碼深度、位置、對手類型）時要明確標出，不要模糊。
5. 若數據不足以下結論，說明需要更多情境參數，不要瞎編。`,
    suggestions: [
      '計算 AA 翻前對大中小對子與結構牌的勝率並做表格',
      'BTN vs BB 的 3bet range 結構是什麼？用 equity 論證',
      '比較不同 stack depth 下 AKo 的 preflop EV',
      '翻牌圈乾燥 vs 濕潤牌面對 C-bet 頻率的影響',
    ],
  },
  course: {
    id: 'course',
    label: '課程學習',
    icon: '📚',
    headerTitle: '撲克課程',
    headerSubtitle: '循序漸進、概念到實戰的結構化學習',
    systemPrompt: `你是一位撲克教學老師，擅長把複雜概念拆成可消化的章節。

你的任務：
1. 使用者問概念時，**從基礎講起，逐步深入**，假設使用者可能是新手。
2. 每個概念搭配**一個具體例子**（常見情境）+ **一個反例**（容易搞錯的地方）。
3. 回答結構：① 定義 ② 為什麼重要 ③ 具體範例 ④ 練習建議。
4. 若使用者正在學某個單元，提出下一步可以學什麼（銜接性）。
5. 需要數據支持時呼叫工具，但重點是概念教學，不是丟一堆數字。`,
    suggestions: [
      '什麼是 pot odds？幫我從零開始講解',
      'GTO 跟 exploitative 打法的差別與適用場景？',
      'range 這個概念為什麼重要？怎麼開始建 range？',
      'preflop 各位置的 open range 教學從 UTG 講起',
    ],
  },
  battle: {
    id: 'battle',
    label: '對戰練習',
    icon: '⚔️',
    headerTitle: '對戰訓練場',
    headerSubtitle: '即時出題、你做決策、AI 打分並給出最佳解',
    systemPrompt: `你是一個撲克對戰練習 AI，負責出題與批改。

你的任務：
1. 使用者問「出題」「我要練習」時，**隨機出一個具體情境**（位置、籌碼、牌、對手行動）讓他決策。
2. 使用者給答案後，**評分並說明最佳解**（用工具算 EV / equity 支持）。
3. 若使用者直接描述一個牌局問「該怎麼打」，**反問他的想法**再給評論（引導思考）。
4. 評分結構：① 他的選擇（分數）② 最佳選擇（理由 + 數據）③ 提示（下次遇到可以想什麼）。
5. 保持節奏感，每輪對話聚焦**一個決策點**，不要灌一堆理論。`,
    suggestions: [
      '出一題 BTN vs BB 的翻前決策讓我練習',
      '給我一個翻牌圈 c-bet 尺寸的練習題',
      '我在 CO 開牌拿到 99，請問該怎麼打？請先問我的想法',
      '出一道 river 大注面對決策的考題',
    ],
  },
}

export const DEFAULT_CHAT_MODE: ChatModeId = 'coach'
