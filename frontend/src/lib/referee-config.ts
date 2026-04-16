export const domain = {
  name: 'Poker Referee AI',
  shortName: 'Poker Ref',
  icon: '\u2660\uFE0F',
  description: 'TDA 2024 Tournament Rules Engine',
  terms: {
    case: 'Dispute',
    ruling: 'Ruling',
    rule: 'Rule',
    knowledgeBase: 'Rule Library',
    confidence: 'Confidence',
    challenge: 'Challenge',
  },
  contextFields: [
    {
      key: 'game_type',
      label: 'Game Type',
      type: 'select' as const,
      options: ['NLHE', 'PLO', 'Limit', 'Stud'],
    },
    {
      key: 'pot_size',
      label: 'Pot Size',
      type: 'number' as const,
      placeholder: '15000',
    },
    {
      key: 'blind_level',
      label: 'Blinds',
      type: 'text' as const,
      placeholder: '500/1000',
    },
  ],
  modes: {
    A: { label: 'Auto Decide', color: 'emerald', desc: 'AI auto-rules (lookup)' },
    B: { label: 'Challengeable', color: 'blue', desc: '30s challenge window' },
    C: { label: 'Human Confirm', color: 'amber', desc: 'Needs human approval' },
    escalated: { label: 'Escalated', color: 'red', desc: 'Forced to human' },
  },
} as const;

export type ModeKey = keyof typeof domain.modes;
export type ContextFieldKey = (typeof domain.contextFields)[number]['key'];
