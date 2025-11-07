'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getAgents, createOrchestration, getOrchestration } from '@/lib/api'

type Agent = {
  id: number
  name: string
  description: string
  run_count: number
  success_count: number
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

  useEffect(() => {
    loadAgents()
  }, [])

  useEffect(() => {
    if (orchestrationId) {
      // Poll for orchestration status
      const interval = setInterval(async () => {
        try {
          const status = await getOrchestration(orchestrationId)
          setOrchestrationStatus(status)

          if (status.status === 'completed' || status.status === 'failed') {
            clearInterval(interval)
            setRunning(false)
          }
        } catch (error) {
          console.error('Failed to poll orchestration:', error)
        }
      }, 2000)

      return () => clearInterval(interval)
    }
  }, [orchestrationId])

  const loadAgents = async () => {
    try {
      setLoading(true)
      const data = await getAgents()
      setAgents(data.agents || [])
    } catch (error) {
      console.error('Failed to load agents:', error)
    } finally {
      setLoading(false)
    }
  }

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
      const result = await createOrchestration(selectedAgentIds, prompt, strategy)
      setOrchestrationId(result.orchestration_id)

      // Start polling
      const status = await getOrchestration(result.orchestration_id)
      setOrchestrationStatus(status)
    } catch (error) {
      console.error('Failed to start orchestration:', error)
      alert('Failed to start orchestration')
      setRunning(false)
    }
  }

  const handleReset = () => {
    setOrchestrationId(null)
    setOrchestrationStatus(null)
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
                  Status: <span className={`font-semibold ${
                    orchestrationStatus.status === 'completed' ? 'text-green-600' :
                    orchestrationStatus.status === 'failed' ? 'text-red-600' :
                    'text-blue-600'
                  }`}>
                    {orchestrationStatus.status}
                  </span>
                </p>
                {orchestrationStatus.strategy && (
                  <p className="text-xs text-gray-500 mt-1">
                    Strategy: {orchestrationStatus.strategy}
                  </p>
                )}
              </div>
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
            {orchestrationStatus.logs && (
              <div className="mb-6">
                <h3 className="font-semibold mb-2">Execution Logs</h3>
                <div className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-auto max-h-96 font-mono text-sm whitespace-pre-wrap">
                  {orchestrationStatus.logs}
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
                          <pre className="text-sm whitespace-pre-wrap">{output}</pre>
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
