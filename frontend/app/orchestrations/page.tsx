'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { API_BASE, getAgents, createOrchestration, getOrchestration } from '@/lib/api'

type Agent = {
  id: number
  name: string
  description: string
  run_count: number
  success_count: number
  default_model?: string
  instructions?: string
}

export default function OrchestrationsPage() {
  const router = useRouter()
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedAgentIds, setSelectedAgentIds] = useState<number[]>([])
  const [prompt, setPrompt] = useState('')
  const [strategy, setStrategy] = useState('manager-led')
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [orchestrationId, setOrchestrationId] = useState<number | null>(null)
  const [orchestrationStatus, setOrchestrationStatus] = useState<any>(null)
  const [orchestrationLogs, setOrchestrationLogs] = useState('')
  const [streamStatus, setStreamStatus] = useState<string | null>(null)
  const [streamingOrchestrationId, setStreamingOrchestrationId] = useState<number | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const orchestrationLogsEndRef = useRef<HTMLDivElement | null>(null)
  const lastRefreshRef = useRef<number>(0)

  const loadAgents = useCallback(async () => {
    try {
      setLoading(true)
      const data = await getAgents()
      setAgents(data.agents || [])
    } catch (error) {
      console.error('Failed to load agents:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  const stopOrchestrationStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setStreamingOrchestrationId(null)
  }, [])

  const refreshOrchestration = useCallback(
    async (id: number, finalize: boolean = false) => {
      try {
        const status = await getOrchestration(id)
        lastRefreshRef.current = Date.now()
        setOrchestrationStatus((prev: any) => {
          if (eventSourceRef.current && !finalize) {
            return {
              ...status,
              logs: prev?.logs ?? '',
            }
          }
          return status
        })

        setStreamStatus(status.status)

        if (!eventSourceRef.current || finalize) {
          setOrchestrationLogs(status.logs || '')
        }

        if (finalize) {
          setRunning(false)
        }
      } catch (error) {
        console.error('Failed to refresh orchestration:', error)
      }
    },
    []
  )

  const startOrchestrationStream = useCallback(
    (id: number) => {
      stopOrchestrationStream()
      setStreamingOrchestrationId(id)
      setOrchestrationLogs('')
      setStreamStatus('running')

      const source = new EventSource(`${API_BASE}/api/orchestrations/${id}/stream`)
      eventSourceRef.current = source

      source.onmessage = async (event) => {
        try {
          const payload = JSON.parse(event.data)

          if (payload.event === 'log') {
            setOrchestrationLogs((prev) => prev + payload.data)
            setOrchestrationStatus((prev: any) =>
              prev
                ? { ...prev, logs: ((prev.logs || '') + payload.data) }
                : prev
            )
            if (Date.now() - lastRefreshRef.current > 1000) {
              await refreshOrchestration(id)
            }
          } else if (payload.event === 'status') {
            setStreamStatus(payload.data)
            const isFinal = payload.data === 'completed' || payload.data === 'failed'
            await refreshOrchestration(id, isFinal)
            if (isFinal) {
              stopOrchestrationStream()
            }
          } else if (payload.event === 'error') {
            console.error('Orchestration stream error:', payload.data)
          }
        } catch (error) {
          console.error('Failed to parse orchestration stream event:', error)
        }
      }

      source.onerror = () => {
        console.error('Orchestration stream encountered an error, closing connection')
        stopOrchestrationStream()
        setRunning(false)
      }
    },
    [refreshOrchestration, stopOrchestrationStream]
  )

  useEffect(() => {
    loadAgents()
  }, [loadAgents])

  useEffect(() => {
    return () => {
      stopOrchestrationStream()
    }
  }, [stopOrchestrationStream])

  useEffect(() => {
    if (orchestrationLogsEndRef.current) {
      orchestrationLogsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [orchestrationLogs, orchestrationStatus?.logs])

  const toggleAgent = (agentId: number) => {
    if (selectedAgentIds.includes(agentId)) {
      setSelectedAgentIds(selectedAgentIds.filter((id) => id !== agentId))
    } else {
      setSelectedAgentIds([...selectedAgentIds, agentId])
    }
  }

  const handleStartOrchestration = async () => {
    if (selectedAgentIds.length === 0 || !prompt.trim()) {
      alert('Please select at least one agent and enter a prompt')
      return
    }

    try {
      setRunning(true)
      setOrchestrationLogs('')
      setStreamStatus('running')
      const result = await createOrchestration(selectedAgentIds, prompt, strategy)
      setOrchestrationId(result.orchestration_id)
      startOrchestrationStream(result.orchestration_id)
      await refreshOrchestration(result.orchestration_id)
    } catch (error) {
      console.error('Failed to start orchestration:', error)
      alert('Failed to start orchestration')
      setRunning(false)
      stopOrchestrationStream()
    }
  }

  const handleReset = () => {
    stopOrchestrationStream()
    setOrchestrationId(null)
    setOrchestrationStatus(null)
    setOrchestrationLogs('')
    setStreamStatus(null)
    setRunning(false)
    setPrompt('')
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-gray-600">Loading agents...</p>
        </div>
      </div>
    )
  }

  if (orchestrationStatus) {
    const status = (streamStatus || orchestrationStatus.status || '').toLowerCase()
    const isCompleted = status === 'completed'
    const isFailed = status === 'failed'
    const isRunning = status === 'running'
    const statusColor = isCompleted
      ? 'text-green-600'
      : isFailed
      ? 'text-red-600'
      : isRunning
      ? 'text-blue-600'
      : 'text-gray-600'
    const statusLabel = isCompleted
      ? '✅ Completed'
      : isFailed
      ? '❌ Failed'
      : isRunning
      ? '🟡 Running'
      : status || 'unknown'
    const logsToDisplay = orchestrationLogs || orchestrationStatus.logs || ''
    const nodeMetrics: Array<Record<string, any>> =
      (Array.isArray(orchestrationStatus.outputs?.node_metrics)
        ? orchestrationStatus.outputs?.node_metrics
        : undefined) ?? []

    return (
      <div className="min-h-screen bg-gray-50 p-8">
        <div className="max-w-4xl mx-auto">
          <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h1 className="text-2xl font-bold text-gray-900">
                  Orchestration #{orchestrationStatus.id}
                </h1>
                <p className="text-sm text-gray-500">
                  Status:{' '}
                  <span className={`font-semibold ${statusColor}`}>
                    {statusLabel}
                  </span>
                </p>
                {orchestrationStatus.strategy && (
                  <p className="text-xs text-gray-500 mt-1">
                    Strategy: {orchestrationStatus.strategy}
                  </p>
                )}
              </div>
              {isRunning && (
                <div className="flex items-center gap-2 text-blue-600 text-sm">
                  <div className="animate-spin h-4 w-4 border-2 border-blue-600 border-t-transparent rounded-full"></div>
                  <span>Running orchestration...</span>
                </div>
              )}
              <button
                onClick={handleReset}
                className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700"
              >
                New Orchestration
              </button>
            </div>

            {orchestrationStatus.prompt && (
              <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <h4 className="font-semibold text-sm text-blue-900 mb-2">Prompt:</h4>
                <p className="text-sm text-blue-800">{orchestrationStatus.prompt}</p>
              </div>
            )}

            {/* Cost and Tokens */}
            {(orchestrationStatus.total_cost || orchestrationStatus.total_tokens) && (
              <div className="mb-4 flex gap-4 text-sm">
                {orchestrationStatus.total_cost && (
                  <span className="px-3 py-1 bg-green-50 text-green-700 rounded">
                    💰 Total Cost: ${orchestrationStatus.total_cost.toFixed(4)}
                  </span>
                )}
                {orchestrationStatus.total_tokens && (
                  <span className="px-3 py-1 bg-blue-50 text-blue-700 rounded">
                    🔤 Total Tokens: {orchestrationStatus.total_tokens.toLocaleString()}
                  </span>
                )}
              </div>
            )}

            {nodeMetrics.length > 0 && (
              <div className="mb-6">
                <h3 className="font-semibold mb-2">Node Metrics</h3>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm text-left text-gray-600 border border-gray-200">
                    <thead className="bg-gray-100 text-xs uppercase text-gray-500">
                      <tr>
                        <th className="px-3 py-2">Node</th>
                        <th className="px-3 py-2">Type</th>
                        <th className="px-3 py-2">Status</th>
                        <th className="px-3 py-2">Model</th>
                        <th className="px-3 py-2">Cost</th>
                        <th className="px-3 py-2">Tokens</th>
                        <th className="px-3 py-2">Completed</th>
                      </tr>
                    </thead>
                    <tbody>
                      {nodeMetrics.map((metric, index) => (
                        <tr key={`${metric.node}-${index}`} className="border-t border-gray-200">
                          <td className="px-3 py-2 font-medium text-gray-900">{metric.node}</td>
                          <td className="px-3 py-2 capitalize">{metric.type || '-'}</td>
                          <td className="px-3 py-2 capitalize">{metric.status || '-'}</td>
                          <td className="px-3 py-2">{metric.model || '-'}</td>
                          <td className="px-3 py-2">
                            {typeof metric.cost === 'number' ? `$${metric.cost.toFixed(4)}` : '—'}
                          </td>
                          <td className="px-3 py-2">
                            {metric.tokens != null ? Number(metric.tokens).toLocaleString() : '—'}
                          </td>
                          <td className="px-3 py-2 text-xs text-gray-500">
                            {metric.completed_at
                              ? new Date(metric.completed_at).toLocaleString()
                              : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Per-Agent Progress */}
            {orchestrationStatus.agent_progress && (
              <div className="mb-6">
                <h3 className="font-semibold mb-3">Agent Progress</h3>
                <div className="space-y-2">
                  {Object.entries(orchestrationStatus.agent_progress).map(([agentId, progress]: [string, any]) => {
                    const agent = agents.find((a) => a.id === parseInt(agentId))
                    return (
                      <div key={agentId} className="flex items-center gap-3">
                        <span className="text-sm text-gray-700 w-32 truncate">
                          {agent?.name || `Agent #${agentId}`}
                        </span>
                        <div className="flex-1 bg-gray-200 rounded-full h-4 overflow-hidden">
                          <div
                            className="bg-blue-600 h-full transition-all duration-500"
                            style={{ width: `${progress}%` }}
                          ></div>
                        </div>
                        <span className="text-sm text-gray-600 w-12 text-right">
                          {progress}%
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Logs */}
            {(logsToDisplay || isRunning) && (
              <div className="mb-6">
                <h3 className="font-semibold mb-2">Execution Logs</h3>
                <div className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-auto max-h-96 font-mono text-sm whitespace-pre-wrap">
                  {logsToDisplay || 'Waiting for logs...'}
                  <div ref={orchestrationLogsEndRef} />
                </div>
              </div>
            )}

            {/* Outputs */}
            {orchestrationStatus.outputs && (
              <div className="mb-6">
                <h3 className="font-semibold mb-2">Output</h3>
                <div className="bg-white p-4 border border-gray-200 rounded-lg">
                  <pre className="text-sm text-gray-600 whitespace-pre-wrap">
                    {JSON.stringify(orchestrationStatus.outputs, null, 2)}
                  </pre>
                </div>
              </div>
            )}

            {/* Per-Agent Outputs */}
            {orchestrationStatus.agent_outputs && Object.keys(orchestrationStatus.agent_outputs).length > 0 && (
              <div className="mb-6">
                <h3 className="font-semibold mb-3">Per-Agent Outputs</h3>
                <div className="space-y-3">
                  {Object.entries(orchestrationStatus.agent_outputs).map(([agentId, output]: [string, any]) => {
                    const agent = agents.find((a) => a.id === parseInt(agentId))
                    return (
                      <details key={agentId} className="border border-gray-200 rounded-lg">
                        <summary className="p-3 cursor-pointer hover:bg-gray-50 font-medium">
                          {agent?.name || `Agent #${agentId}`}
                        </summary>
                        <div className="p-4 bg-gray-50 border-t border-gray-200">
                          <pre className="text-sm whitespace-pre-wrap">
                            {typeof output === 'string'
                              ? output
                              : JSON.stringify(output, null, 2)}
                          </pre>
                        </div>
                      </details>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Error */}
            {orchestrationStatus.error && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                <h4 className="font-semibold text-red-900 mb-2">Error:</h4>
                <p className="text-sm text-red-800">{orchestrationStatus.error}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Multi-Agent Orchestration
          </h1>
          <p className="text-gray-600">
            Select multiple agents and give them a collaborative task to work on together.
          </p>
        </div>

        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Select Agents</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {agents.map((agent) => (
              <label
                key={agent.id}
                className={`flex items-start p-4 border rounded-lg cursor-pointer transition-colors ${
                  selectedAgentIds.includes(agent.id)
                    ? 'bg-blue-50 border-blue-500'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <input
                  type="checkbox"
                  checked={selectedAgentIds.includes(agent.id)}
                  onChange={() => toggleAgent(agent.id)}
                  className="mt-1 mr-3"
                />
                <div className="flex-1">
                  <div className="font-semibold text-gray-900">{agent.name}</div>
                  {agent.description && (
                    <div className="text-sm text-gray-600 mt-1 line-clamp-2">
                      {agent.description}
                    </div>
                  )}
                  {agent.default_model && (
                    <div className="text-xs text-gray-500 mt-1">
                      Model: {agent.default_model}
                    </div>
                  )}
                  <div className="text-xs text-gray-500 mt-2">
                    {agent.run_count} runs • {agent.success_count} successful
                  </div>
                </div>
              </label>
            ))}
          </div>

          {selectedAgentIds.length > 0 && (
            <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded">
              <p className="text-sm text-blue-900">
                <strong>{selectedAgentIds.length}</strong> agent(s) selected
              </p>
            </div>
          )}
        </div>

        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Orchestration Strategy</h2>
          <div className="space-y-2">
            {[
              {
                value: 'manager-led',
                label: 'Manager-Led',
                description: 'A manager agent coordinates and delegates tasks to selected agents',
              },
              {
                value: 'sequential',
                label: 'Sequential',
                description: 'Agents execute one after another, passing results forward',
              },
              {
                value: 'parallel',
                label: 'Parallel',
                description: 'All agents execute simultaneously on the same prompt',
              },
            ].map((strategyOption) => (
              <label
                key={strategyOption.value}
                className={`flex items-start p-3 border rounded cursor-pointer transition-colors ${
                  strategy === strategyOption.value
                    ? 'bg-blue-50 border-blue-500'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <input
                  type="radio"
                  value={strategyOption.value}
                  checked={strategy === strategyOption.value}
                  onChange={(e) => setStrategy(e.target.value)}
                  className="mt-1 mr-3"
                />
                <div>
                  <div className="font-medium text-gray-900">{strategyOption.label}</div>
                  <div className="text-sm text-gray-600">{strategyOption.description}</div>
                </div>
              </label>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Task Prompt</h2>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[150px] font-mono text-sm"
            placeholder="Enter the task or question for the agents to collaborate on..."
            disabled={running}
          />
        </div>

        <div className="flex justify-end">
          <button
            onClick={handleStartOrchestration}
            disabled={selectedAgentIds.length === 0 || !prompt.trim() || running}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors text-lg font-semibold"
          >
            {running ? 'Starting Orchestration...' : 'Start Orchestration'}
          </button>
        </div>
      </div>
    </div>
  )
}
