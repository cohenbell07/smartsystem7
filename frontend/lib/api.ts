/**
 * API client for Agent Factory backend
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface Project {
  id: number
  question: string
  status: string
  sources_count: number
  research_brief?: string
  viability_score?: number
  viability_rationale?: string
  sensitivity_analysis?: string
  agent_spec?: any
  created_at: string
  updated_at: string
  completed_at?: string
  runs: Run[]
}

export interface Run {
  id: number
  agent_id?: number
  project_id?: number
  status: string
  inputs?: any
  outputs?: any
  logs?: string
  error?: string
  started_at?: string
  completed_at?: string
  cost_estimate?: number
  actual_cost?: number
  cost_breakdown?: any
  total_tokens?: number
}

export interface CostEstimate {
  total_estimated_cost: number
  breakdown: Array<{
    model: string
    role: string
    estimated_input_tokens: number
    estimated_output_tokens: number
    estimated_cost: number
    price_per_1m_input: number
    price_per_1m_output: number
  }>
  warning: string
  estimated_at: string
}

export interface Pricing {
  models: Array<{
    name: string
    input_price_per_1m: number
    output_price_per_1m: number
    provider: string
  }>
  updated_at?: string
  currency: string
}

/**
 * Ask a new question and start research
 */
export async function askQuestion(question: string, email?: string) {
  const res = await fetch(`${API_BASE}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, email }),
  })

  if (!res.ok) {
    throw new Error('Failed to submit question')
  }

  return res.json()
}

/**
 * Get project details
 */
export async function getProject(projectId: number): Promise<Project> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}`)

  if (!res.ok) {
    throw new Error('Failed to fetch project')
  }

  return res.json()
}

/**
 * Get cost estimate for a run
 */
export async function estimateCost(
  projectId?: number,
  agentId?: number,
  inputs: any = {}
): Promise<CostEstimate> {
  const res = await fetch(`${API_BASE}/api/estimate-cost`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId, agent_id: agentId, inputs }),
  })

  if (!res.ok) {
    throw new Error('Failed to estimate cost')
  }

  return res.json()
}

/**
 * Run an agent
 */
export async function runAgent(
  projectId?: number,
  agentId?: number,
  inputs: any = {}
) {
  const res = await fetch(`${API_BASE}/api/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId, agent_id: agentId, inputs }),
  })

  if (!res.ok) {
    throw new Error('Failed to run agent')
  }

  return res.json()
}

/**
 * Get run details
 */
export async function getRun(runId: number): Promise<Run> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}`)

  if (!res.ok) {
    throw new Error('Failed to fetch run')
  }

  return res.json()
}

/**
 * Save agent to portfolio
 */
export async function saveAgent(
  projectId: number,
  name: string,
  description?: string
) {
  const res = await fetch(`${API_BASE}/api/save-agent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId, name, description }),
  })

  if (!res.ok) {
    throw new Error('Failed to save agent')
  }

  return res.json()
}

/**
 * Get current pricing for all models
 */
export async function getPricing(): Promise<Pricing> {
  const res = await fetch(`${API_BASE}/api/pricing`)

  if (!res.ok) {
    throw new Error('Failed to fetch pricing')
  }

  return res.json()
}

/**
 * List all agents
 */
export async function listAgents() {
  const res = await fetch(`${API_BASE}/api/agents`)

  if (!res.ok) {
    throw new Error('Failed to fetch agents')
  }

  return res.json()
}

/**
 * Get all agents (alias for listAgents)
 */
export async function getAgents() {
  return listAgents()
}

/**
 * Get agent details
 */
export async function getAgent(agentId: number) {
  const res = await fetch(`${API_BASE}/api/agents/${agentId}`)

  if (!res.ok) {
    throw new Error('Failed to fetch agent')
  }

  return res.json()
}

/**
 * Get secrets (API keys)
 */
export async function getSecrets() {
  const res = await fetch(`${API_BASE}/api/settings/secrets`)

  if (!res.ok) {
    throw new Error('Failed to fetch secrets')
  }

  return res.json()
}

/**
 * Update secrets (API keys)
 */
export async function updateSecrets(secrets: Record<string, string>) {
  const res = await fetch(`${API_BASE}/api/settings/secrets`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ secrets }),
  })

  if (!res.ok) {
    throw new Error('Failed to update secrets')
  }

  return res.json()
}

/**
 * Validate API keys for an agent
 */
export async function validateAgentKeys(projectId?: number, agentId?: number) {
  const res = await fetch(`${API_BASE}/api/agents/validate-keys`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId, agent_id: agentId }),
  })

  if (!res.ok) {
    throw new Error('Failed to validate API keys')
  }

  return res.json()
}
