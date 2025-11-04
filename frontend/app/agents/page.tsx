'use client'

import useSWR from 'swr'
import Link from 'next/link'
import { getAgents } from '@/lib/api'
import { formatTimeAgo } from '@/lib/utils'

export default function AgentsPage() {
  const { data, error } = useSWR('agents', getAgents)

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

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">My Agents</h1>
        <p className="text-gray-600">
          Saved agents ready to run with new inputs
        </p>
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
    </div>
  )
}
