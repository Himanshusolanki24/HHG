import { z } from 'zod'

export const Trigger = z.enum(['risk_score', 'customer_report', 'analyst_request'])
export const CaseStatus = z.enum(['open', 'awaiting_evidence', 'ready_to_act', 'closed'])
export const Pattern = z.enum([
  'card_testing', 'account_takeover', 'mule_network', 'app_scam', 'synthetic_identity', 'friendly_fraud',
])
export const EntityType = z.enum(['account', 'card', 'device', 'email', 'ip', 'transaction', 'prior_case'])
export const Route = z.enum(['auto_execute', 'analyst_approval', 'dual_approval'])
export const Tool = z.enum([
  'gsql', 'graphrag', 'policy_lookup', 'evidence_request', 'evidence_response', 'recommend',
])

const unit = z.number().min(0).max(1)

export const Case = z.object({
  id: z.string(),
  title: z.string(),
  trigger: Trigger,
  pattern: Pattern,
  status: CaseStatus,
  risk: unit,
  confidence: unit,
  stateSince: z.iso.datetime(),
  hasRun: z.boolean(),
})

export const Policy = z.object({
  id: z.string(),
  doc: z.string(),
  clause: z.string(),
  title: z.string(),
  text: z.string(),
})

export const GraphNode = z.object({
  id: z.string(),
  type: EntityType,
  label: z.string(),
  risk: unit,
  attrs: z.record(z.string(), z.union([z.string(), z.number()])),
})

export const GraphEdge = z.object({
  id: z.string(),
  source: z.string(),
  target: z.string(),
  rel: z.string(),
  weight: z.number(),
})

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

export const Unknown = z.object({
  id: z.string(),
  question: z.string(),
  resolvedBy: z.string(),
  infoGain: z.number().min(0),
  resolved: z.boolean(),
})

export const ActionOption = z.object({
  id: z.string(),
  label: z.string(),
  allowed: z.boolean(),
  policyId: z.string(),
  reason: z.string().optional(),
})

export const Recommendation = z.object({
  id: z.string(),
  action: z.string(),
  route: Route,
  policyId: z.string(),
  risk: unit,
  riskLo: unit,
  riskHi: unit,
  confidence: unit,
  rationale: z.string(),
  unknowns: z.array(Unknown),
  actions: z.array(ActionOption),
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
  delayMs: z.number().optional(), // mock stream pacing only
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

export const Investigation = z.object({
  caseId: z.string(),
  subjectId: z.string(),
  alertAt: z.iso.datetime(),
  nodes: z.array(GraphNode),
  edges: z.array(GraphEdge),
  transactions: z.array(Transaction),
  similar: z.array(SimilarCase),
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
export type Recommendation = z.infer<typeof Recommendation>
export type ActionOption = z.infer<typeof ActionOption>
export type AgentStep = z.infer<typeof AgentStep>
export type Transaction = z.infer<typeof Transaction>
export type SimilarCase = z.infer<typeof SimilarCase>
export type Investigation = z.infer<typeof Investigation>
export type AuditEntry = z.infer<typeof AuditEntry>
