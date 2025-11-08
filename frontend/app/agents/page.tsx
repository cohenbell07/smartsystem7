'use client'

import { useState } from 'react'
import useSWR from 'swr'
import Link from 'next/link'
import { getAgents } from '@/lib/api'
import { formatTimeAgo } from '@/lib/utils'

export default function AgentsPage() {
  const { data, error } = useSWR('agents', getAgents)
  const [showCombineModal, setShowCombineModal] = useState(false)
  const [selectedAgents, setSelectedAgents] = useState<number[]>([])
  const [chainName, setChainName] = useState('')
  const [chainGoal, setChainGoal] = useState('')
  const [chainStrategy, setChainStrategy] = useState<'sequential' | 'parallel' | 'manager-led'>('sequential')
  const [isCreatingChain, setIsCreatingChain] = useState(false)
  const [chainError, setChainError] = useState<string | null>(null)
  const [chainSuccess, setChainSuccess] = useState<string | null>(null)

  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          Failed to load agents
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading agents...</p>
        </div>
      </div>
    )
  }

  const agents = data.agents || []

  const toggleAgentSelection = (agentId: number) => {
    setSelectedAgents((prev) =>
      prev.includes(agentId)
        ? prev.filter((id) => id !== agentId)
        : [...prev, agentId]
    )
  }

  const handleCreateChain = async () => {
    if (selectedAgents.length < 2) {
      setChainError('Please select at least 2 agents to combine')
      return
    }

    if (!chainName.trim() || !chainGoal.trim()) {
      setChainError('Please provide a chain name and goal')
      return
    }

    setIsCreatingChain(true)
    setChainError(null)
    setChainSuccess(null)

    try {
      const response = await fetch(`${API_URL}/api/agents/chain-build`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chain_name: chainName,
          agent_ids: selectedAgents,
          goal: chainGoal,
          strategy: chainStrategy,
        }),
      })

      if (!response.ok) {
        throw new Error('Failed to create chain build')
      }

      const result = await response.json()
      setChainSuccess(`Chain build created successfully! Chain ID: ${result.chain_id}`)

      // Reset form
      setTimeout(() => {
        setShowCombineModal(false)
        setSelectedAgents([])
        setChainName('')
        setChainGoal('')
        setChainStrategy('sequential')
        setChainSuccess(null)
      }, 2000)
    } catch (err) {
      setChainError(err instanceof Error ? err.message : 'Failed to create chain build')
    } finally {
      setIsCreatingChain(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">My Agents</h1>
          <p className="text-gray-600">
            Saved agents ready to run with new inputs
          </p>
        </div>
        {agents.length >= 2 && (
          <button
            onClick={() => setShowCombineModal(true)}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors flex items-center gap-2"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
            Combine Agents
          </button>
        )}
      </div>

      {agents.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <h2 className="text-xl font-medium text-gray-900 mb-2">No agents yet</h2>
          <p className="text-gray-600 mb-6">
            Create your first agent by asking a question and saving the generated agent.
          </p>
          <Link
            href="/"
            className="inline-block px-6 py-3 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors"
          >
            Ask a Question
          </Link>
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent: any) => (
            <div key={agent.id} className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                {agent.name}
              </h3>
              <p className="text-gray-600 text-sm mb-4 line-clamp-2">
                {agent.description}
              </p>

              <div className="flex items-center justify-between text-sm text-gray-500 mb-4">
                <span>{agent.run_count} runs</span>
                <span>{agent.success_count} successful</span>
              </div>

              <div className="text-xs text-gray-400 mb-4">
                Created {formatTimeAgo(agent.created_at)}
              </div>

              <div className="flex gap-2">
                <Link
                  href={`/agents/${agent.id}`}
                  className="flex-1 text-center px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors text-sm"
                >
                  View
                </Link>
                <button
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm"
                  onClick={() => {
                    // TODO: Open run modal
                    alert('Run modal coming soon!')
                  }}
                >
                  Run
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Combine Agents Modal */}
      {showCombineModal && (
        <div className="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="px-6 py-4 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-medium text-gray-900">Combine Agents</h3>
                <button
                  onClick={() => {
                    setShowCombineModal(false)
                    setSelectedAgents([])
                    setChainError(null)
                  }}
                  className="text-gray-400 hover:text-gray-500"
                >
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            <div className="px-6 py-4 space-y-4">
              {chainError && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
                  {chainError}
                </div>
              )}

              {chainSuccess && (
                <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg">
                  {chainSuccess}
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Chain Name
                </label>
                <input
                  type="text"
                  value={chainName}
                  onChange={(e) => setChainName(e.target.value)}
                  placeholder="e.g., Research and Build Chain"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Goal
                </label>
                <textarea
                  value={chainGoal}
                  onChange={(e) => setChainGoal(e.target.value)}
                  placeholder="Describe what you want this chain of agents to accomplish..."
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Execution Strategy
                </label>
                <select
                  value={chainStrategy}
                  onChange={(e) => setChainStrategy(e.target.value as any)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  <option value="sequential">Sequential (one after another)</option>
                  <option value="parallel">Parallel (all at once)</option>
                  <option value="manager-led">Manager-led (coordinated)</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Select Agents ({selectedAgents.length} selected)
                </label>
                <div className="space-y-2 max-h-64 overflow-y-auto border border-gray-200 rounded-md p-3">
                  {agents.map((agent: any) => (
                    <label
                      key={agent.id}
                      className="flex items-center p-2 hover:bg-gray-50 rounded cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selectedAgents.includes(agent.id)}
                        onChange={() => toggleAgentSelection(agent.id)}
                        className="h-4 w-4 text-purple-600 focus:ring-purple-500 border-gray-300 rounded"
                      />
                      <div className="ml-3 flex-1">
                        <div className="text-sm font-medium text-gray-900">{agent.name}</div>
                        <div className="text-xs text-gray-500">{agent.description}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 flex gap-3">
              <button
                onClick={() => {
                  setShowCombineModal(false)
                  setSelectedAgents([])
                  setChainError(null)
                }}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateChain}
                disabled={isCreatingChain || selectedAgents.length < 2}
                className="flex-1 px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                {isCreatingChain ? 'Creating...' : 'Create Chain Build'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
