'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import useSWR from 'swr'
import { getProject, saveAgent } from '@/lib/api'
import { formatTimeAgo } from '@/lib/utils'

export default function ProjectPage() {
  const params = useParams()
  const projectId = parseInt(params.id as string)

  const { data, error, mutate } = useSWR(
    `project-${projectId}`,
    () => getProject(projectId),
    { refreshInterval: 3000 } // Poll every 3 seconds
  )

  const [savingAgent, setSavingAgent] = useState(false)
  const [agentName, setAgentName] = useState('')

  const handleSaveAgent = async () => {
    if (!agentName.trim()) {
      alert('Please enter an agent name')
      return
    }

    setSavingAgent(true)
    try {
      await saveAgent(projectId, agentName, data.question)
      alert('Agent saved to portfolio!')
      setAgentName('')
    } catch (err) {
      alert('Failed to save agent')
      console.error(err)
    } finally {
      setSavingAgent(false)
    }
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          Failed to load project
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading project...</p>
        </div>
      </div>
    )
  }

  const viability = data.viability_rationale ? JSON.parse(data.viability_rationale) : null

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">{data.question}</h1>
            <p className="text-sm text-gray-500">
              Created {formatTimeAgo(data.created_at)} • Status: <span className="font-medium">{data.status}</span>
            </p>
          </div>
          <div className={`px-4 py-2 rounded-full text-sm font-medium ${
            data.status === 'completed' ? 'bg-green-100 text-green-800' :
            data.status === 'failed' ? 'bg-red-100 text-red-800' :
            'bg-yellow-100 text-yellow-800'
          }`}>
            {data.status.toUpperCase()}
          </div>
        </div>
      </div>

      {/* Viability Score */}
      {data.viability_score !== null && (
        <div className="bg-white rounded-lg shadow mb-8 p-6">
          <h2 className="text-xl font-semibold mb-4">Business Viability Score</h2>
          <div className="flex items-center mb-6">
            <div className="text-6xl font-bold text-primary">{data.viability_score}</div>
            <div className="ml-4 text-gray-600">/100</div>
          </div>

          {viability && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div>
                <div className="text-sm text-gray-500">Market Demand</div>
                <div className="text-2xl font-semibold">{viability.market_demand}</div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Competition</div>
                <div className="text-2xl font-semibold">{viability.competition}</div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Feasibility</div>
                <div className="text-2xl font-semibold">{viability.feasibility}</div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Capital</div>
                <div className="text-2xl font-semibold">{viability.capital_requirement}</div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Moat</div>
                <div className="text-2xl font-semibold">{viability.moat}</div>
              </div>
            </div>
          )}

          {viability?.rationale && (
            <div className="mt-6 pt-6 border-t">
              <h3 className="font-medium mb-2">Rationale</h3>
              <p className="text-gray-700 whitespace-pre-wrap">{viability.rationale}</p>
            </div>
          )}
        </div>
      )}

      {/* Research Brief */}
      {data.research_brief && (
        <div className="bg-white rounded-lg shadow mb-8 p-6">
          <h2 className="text-xl font-semibold mb-4">
            Research Brief
            <span className="ml-2 text-sm font-normal text-gray-500">
              ({data.sources_count} sources)
            </span>
          </h2>
          <div className="prose max-w-none">
            <div className="whitespace-pre-wrap">{data.research_brief}</div>
          </div>
        </div>
      )}

      {/* Agent Spec */}
      {data.agent_spec && (
        <div className="bg-white rounded-lg shadow mb-8 p-6">
          <h2 className="text-xl font-semibold mb-4">Proposed Agent</h2>
          <div className="mb-6">
            <h3 className="font-medium text-lg">{data.agent_spec.name}</h3>
            <p className="text-gray-600">{data.agent_spec.description}</p>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <h4 className="font-medium mb-2">Required Tools</h4>
              <ul className="list-disc list-inside text-gray-700">
                {data.agent_spec.tools?.map((tool: string, i: number) => (
                  <li key={i}>{tool}</li>
                ))}
              </ul>
            </div>

            <div>
              <h4 className="font-medium mb-2">Required APIs</h4>
              {data.agent_spec.apis?.length > 0 ? (
                <ul className="list-disc list-inside text-gray-700">
                  {data.agent_spec.apis.map((api: any, i: number) => (
                    <li key={i}>{typeof api === 'string' ? api : api.name}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-gray-500">No external APIs required</p>
              )}
            </div>
          </div>

          {/* Save Agent */}
          <div className="mt-6 pt-6 border-t">
            <h4 className="font-medium mb-3">Save to Portfolio</h4>
            <div className="flex gap-3">
              <input
                type="text"
                placeholder="Agent name..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                value={agentName}
                onChange={(e) => setAgentName(e.target.value)}
              />
              <button
                onClick={handleSaveAgent}
                disabled={savingAgent}
                className="px-6 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {savingAgent ? 'Saving...' : 'Save Agent'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Loading States */}
      {data.status === 'researching' && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <div className="flex items-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mr-4"></div>
            <div>
              <h3 className="font-medium text-blue-900">Researching...</h3>
              <p className="text-sm text-blue-700">Crawling 50+ sources</p>
            </div>
          </div>
        </div>
      )}

      {data.status === 'analyzing' && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <div className="flex items-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mr-4"></div>
            <div>
              <h3 className="font-medium text-blue-900">Analyzing...</h3>
              <p className="text-sm text-blue-700">Synthesizing research and calculating viability</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
