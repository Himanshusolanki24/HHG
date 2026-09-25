import { z } from 'zod'

export const Trigger = z.enum(['risk_score', 'customer_report', 'analyst_request'])
export const CaseStatus = z.enum(['open', 'awaiting_evidence', 'ready_to_act', 'closed'])
export const Pattern = z.enum([
  'card_testing', 'card_not_present_fraud', 'card_not_present_new_device', 'out_of_region_use', 'account_takeover', 'undocumented', 'none',
])
export const EntityType = z.enum(['customer', 'card', 'transaction', 'device', 'email', 'region', 'prior_case'])
export const Route = z.enum(['auto', 'L1', 'L2'])
export const Verdict = z.enum(['fraud', 'legitimate', 'uncertain'])
export const Tool = z.enum(['gsql', 'graphrag', 'policy_lookup', 'evidence_request', 'evidence_response', 'recommend'])

const unit = z.number().min(0).max(1)

/** Queue row. `risk` is the agent's fraud probability; `modelScore` is the bank model's input score. */
export const Case = z.object({
  id: z.string(),
  title: z.string(),
  trigger: Trigger,
  pattern: Pattern,
  status: CaseStatus,
  risk: unit,
  confidence: unit,
  modelScore: unit.nullable(),
  stateSince: z.iso.datetime(),
  hasRun: z.boolean(),
  cardId: z.string(),
  firstAction: z.string(),
})

export const Policy = z.object({ id: z.string(), doc: z.string(), clause: z.string(), title: z.string(), text: z.string() })

export const GraphNode = z.object({
  id: z.string(),
  type: EntityType,
  label: z.string(),
  risk: unit,
  attrs: z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.null()])),
})
export const GraphEdge = z.object({ id: z.string(), source: z.string(), target: z.string(), rel: z.string(), weight: z.number() })

export const Evidence = z.object({
  id: z.string(),
  kind: z.enum(['graph', 'policy', 'external', 'retrieval']),
  label: z.string(),
  summary: z.string(),
  source: z.string(),
  nodes: z.array(z.string()),
})

export const Claim = z.object({
  text: z.string(),
  ref: z.object({ kind: z.enum(['node', 'policy', 'evidence']), id: z.string() }),
})

/** One recommended action, exactly as it appears in the answer file. `reason` starts with the rule id ("R2: ..."). */
export const Action = z.object({ action: z.string(), route: Route, reason: z.string() })

export const Unknown = z.object({ id: z.string(), question: z.string(), infoGain: z.number().min(0), resolved: z.boolean() })

export const Recommendation = z.object({
  id: z.string(),
  stage: z.enum(['initial', 'final']),
  verdict: Verdict,
  pattern: Pattern,
  p: unit,
  pLo: unit,
  pHi: unit,
  actions: z.array(Action),
  unknowns: z.array(Unknown),
  causedBy: z.array(z.string()),
})

export const AgentStep = z.object({
  id: z.string(),
  seq: z.number().int(),
  at: z.iso.datetime(),
  tool: Tool,
  title: z.string(),
  input: z.string(),
  summary: z.string(),
  latencyMs: z.number(),
  tokens: z.object({ in: z.number(), out: z.number() }),
  claims: z.array(Claim),
  nodes: z.array(z.string()),
  edges: z.array(z.string()),
  evidence: Evidence.optional(),
  recommendation: Recommendation.optional(),
})

export const Transaction = z.object({
  id: z.string(),
  at: z.iso.datetime(),
  amount: z.number(),
  merchant: z.string(),
  direction: z.enum(['in', 'out']),
  flagged: z.boolean(),
})

export const SimilarCase = z.object({
  caseId: z.string(),
  similarity: unit,
  outcome: z.enum(['confirmed_fraud', 'false_positive', 'inconclusive']),
  decision: z.string(),
  analystNote: z.string(),
})

/** The submitted answer file (dataset README, "Answer Format"). Validated loosely: the backend's validate.py is strict. */
export const Answer = z.object({
  case_id: z.string(),
  case: z.object({
    status: z.enum(['open', 'closed_fraud', 'closed_legitimate', 'escalated']),
    verdict: Verdict,
    fraud_probability: unit,
    pattern: Pattern,
    pattern_description: z.string(),
    affected_txn_ids: z.array(z.string()),
    first_suspicious_txn_id: z.string(),
    connected_card_ids: z.array(z.string()),
    connected_device_profiles: z.array(z.string()),
    exposure_usd: z.number(),
    evidence: z.array(z.object({ claim: z.string(), source: z.string(), ref: z.string(), entity_ids: z.array(z.string()) })),
    similar_prior_cases: z.array(z.string()),
    summary: z.string(),
    written_to_graph: z.boolean(),
    graph_case_id: z.string(),
  }),
  evidence_requests: z.array(z.object({ type: z.string(), asked_after_step: z.number(), assumed_response: z.string() })),
  next_best_actions: z.object({ initial: z.array(Action), final: z.array(Action), what_changed: z.string() }),
  sar: z.object({
    file: z.boolean(), reason: z.string(), narrative: z.string(), subjects: z.array(z.string()),
    total_amount_usd: z.number(), activity_dates: z.array(z.string()),
  }),
  stop_reason: z.string(),
  tool_calls: z.number(),
  tokens: z.number(),
  latency_s: z.number(),
})

export const Investigation = z.object({
  caseId: z.string(),
  subjectId: z.string(),
  alertAt: z.iso.datetime(),
  nodes: z.array(GraphNode),
  edges: z.array(GraphEdge),
  transactions: z.array(Transaction),
  similar: z.array(SimilarCase),
  answer: Answer,
  steps: z.array(AgentStep),
})

export const AuditEntry = z.object({
  id: z.string(),
  at: z.iso.datetime(),
  caseId: z.string(),
  actionId: z.string(),
  label: z.string(),
  actor: z.string(),
  status: z.enum(['pending', 'committed', 'rolled_back']),
  error: z.string().optional(),
})

export type Case = z.infer<typeof Case>
export type CaseStatus = z.infer<typeof CaseStatus>
export type Pattern = z.infer<typeof Pattern>
export type Policy = z.infer<typeof Policy>
export type GraphNode = z.infer<typeof GraphNode>
export type GraphEdge = z.infer<typeof GraphEdge>
export type EntityType = z.infer<typeof EntityType>
export type Evidence = z.infer<typeof Evidence>
export type Claim = z.infer<typeof Claim>
export type Action = z.infer<typeof Action>
export type Recommendation = z.infer<typeof Recommendation>
export type AgentStep = z.infer<typeof AgentStep>
export type Transaction = z.infer<typeof Transaction>
export type SimilarCase = z.infer<typeof SimilarCase>
export type Answer = z.infer<typeof Answer>
export type Investigation = z.infer<typeof Investigation>
export type AuditEntry = z.infer<typeof AuditEntry>
