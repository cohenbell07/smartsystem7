'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import {
  getAgent,
  runAgentWithPrompt,
  getRun,
  getAgentFiles,
  createAgentRepo,
  type Run,
} from '@/lib/api'
import ApiKeyModal from '@/components/ApiKeyModal'

type Agent = {
  id: number
  name: string
  description: string
  agent_spec: any
  source_project_id?: number
  run_count: number
  success_count: number
  repo_url?: string
  repo_local_path?: string
  created_at: string
  runs: Array<{
    id: number
    status: string
    started_at?: string
    completed_at?: string
    prompt?: string
  }>
}

type FileItem = {
  path: string
  name: string
  size: number
  content: string
}

type TabType = 'run' | 'logs' | 'files' | 'memory' | 'code'

export default function AgentDetailPage() {
  const params = useParams()
  const agentId = params.id as string

  const [agent, setAgent] = useState<Agent | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<TabType>('run')
  const [prompt, setPrompt] = useState('')
  const [currentRun, setCurrentRun] = useState<Run | null>(null)
  const [running, setRunning] = useState(false)
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null)

  // API key modal
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [missingKeys, setMissingKeys] = useState<any[]>([])

  // Files
  const [files, setFiles] = useState<FileItem[]>([])
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null)
  const [creatingRepo, setCreatingRepo] = useState(false)

  useEffect(() => {
    loadAgent()
  }, [agentId])

  useEffect(() => {
    // Cleanup polling on unmount
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
    }
  }, [pollingInterval])

  const loadAgent = async () => {
    try {
      setLoading(true)
      const data = await getAgent(parseInt(agentId))
      setAgent(data)

      // Load files if repo exists
      if (data.repo_url) {
        loadFiles()
      }
    } catch (error) {
      console.error('Failed to load agent:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadFiles = async () => {
    try {
      const data = await getAgentFiles(parseInt(agentId))
      setFiles(data.files || [])
    } catch (error) {
      console.error('Failed to load files:', error)
    }
  }

  const handleCreateRepo = async () => {
    if (creatingRepo) return

    try {
      setCreatingRepo(true)
      await createAgentRepo(parseInt(agentId))
      await loadAgent()
      alert('Repository created successfully!')
    } catch (error: any) {
      if (error.status === 428) {
        // Missing GitHub token
        setMissingKeys(error.missing_with_instructions || [])
        setShowKeyModal(true)
      } else {
        console.error('Failed to create repo:', error)
        alert('Failed to create repository. Please check your GitHub token.')
      }
    } finally {
      setCreatingRepo(false)
    }
  }

  const startPolling = (runId: number) => {
    // Poll every 2 seconds
    const interval = setInterval(async () => {
      try {
        const runData = await getRun(runId)
        setCurrentRun(runData)

        // Stop polling if completed or failed
        if (runData.status === 'completed' || runData.status === 'failed') {
          clearInterval(interval)
          setPollingInterval(null)
          setRunning(false)
          // Reload agent to update run history
          loadAgent()
        }
      } catch (error) {
        console.error('Failed to poll run:', error)
      }
    }, 2000)

    setPollingInterval(interval)
  }

  const handleRunPrompt = async () => {
    if (!prompt.trim() || running) return

    try {
      setRunning(true)
      const result = await runAgentWithPrompt(parseInt(agentId), prompt)

      // Start polling for updates
      startPolling(result.run_id)

      // Load initial run data
      const runData = await getRun(result.run_id)
      setCurrentRun(runData)
      setActiveTab('logs')
    } catch (error: any) {
      console.error('Failed to run agent:', error)

      // Check for 428 status (missing API keys)
      if (error.status === 428) {
        setMissingKeys(error.missing_with_instructions || [])
        setShowKeyModal(true)
        setRunning(false)
      } else {
        alert('Failed to run agent. Please try again.')
        setRunning(false)
      }
    }
  }

  const handleKeysSuccess = async () => {
    setShowKeyModal(false)
    // Retry the run
    if (prompt.trim()) {
      setTimeout(() => handleRunPrompt(), 500)
    }
  }

  const renderRunTab = () => (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Enter your prompt:
        </label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[150px] font-mono text-sm"
          placeholder="Enter your task or question for the agent..."
          disabled={running}
        />
      </div>

      <button
        onClick={handleRunPrompt}
        disabled={!prompt.trim() || running}
        className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
      >
        {running ? 'Running...' : 'Run Agent'}
      </button>

      {agent && agent.runs.length > 0 && (
        <div className="mt-8">
          <h3 className="text-lg font-semibold mb-4">Recent Runs</h3>
          <div className="space-y-2">
            {agent.runs.slice(0, 10).map((run) => (
              <div
                key={run.id}
                className="p-4 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer"
                onClick={async () => {
                  const runData = await getRun(run.id)
                  setCurrentRun(runData)
                  setActiveTab('logs')
                }}
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-1 text-xs rounded ${
                        run.status === 'completed' ? 'bg-green-100 text-green-800' :
                        run.status === 'failed' ? 'bg-red-100 text-red-800' :
                        run.status === 'running' ? 'bg-blue-100 text-blue-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {run.status}
                      </span>
                      <span className="text-sm text-gray-500">
                        Run #{run.id}
                      </span>
                    </div>
                    {run.prompt && (
                      <p className="mt-2 text-sm text-gray-700 line-clamp-2">
                        {run.prompt}
                      </p>
                    )}
                  </div>
                  <div className="text-xs text-gray-500">
                    {run.started_at && new Date(run.started_at).toLocaleString()}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )

  const renderLogsTab = () => {
    if (!currentRun) {
      return (
        <div className="text-center text-gray-500 py-8">
          No run selected. Run the agent first or select a run from the history.
        </div>
      )
    }

    return (
      <div className="space-y-6">
        <div>
          <div className="flex justify-between items-start mb-4">
            <div>
              <h3 className="text-lg font-semibold">Run #{currentRun.id}</h3>
              <p className="text-sm text-gray-500">
                Status: <span className={`font-semibold ${
                  currentRun.status === 'completed' ? 'text-green-600' :
                  currentRun.status === 'failed' ? 'text-red-600' :
                  currentRun.status === 'running' ? 'text-blue-600' :
                  'text-gray-600'
                }`}>
                  {currentRun.status}
                </span>
              </p>

              {/* Cost and Token Display */}
              {(currentRun.total_cost || currentRun.total_tokens) && (
                <div className="mt-2 flex gap-4 text-xs">
                  {currentRun.total_cost && (
                    <span className="px-2 py-1 bg-green-50 text-green-700 rounded">
                      💰 Cost: ${currentRun.total_cost.toFixed(4)}
                    </span>
                  )}
                  {currentRun.total_tokens && (
                    <span className="px-2 py-1 bg-blue-50 text-blue-700 rounded">
                      🔤 Tokens: {currentRun.total_tokens.toLocaleString()}
                    </span>
                  )}
                </div>
              )}
            </div>
            {running && (
              <div className="flex items-center gap-2 text-blue-600">
                <div className="animate-spin h-4 w-4 border-2 border-blue-600 border-t-transparent rounded-full"></div>
                <span className="text-sm">Running...</span>
              </div>
            )}
          </div>

          {currentRun.prompt && (
            <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <h4 className="font-semibold text-sm text-blue-900 mb-2">Prompt:</h4>
              <p className="text-sm text-blue-800">{currentRun.prompt}</p>
            </div>
          )}
        </div>

        <div>
          <h4 className="font-semibold mb-2">Execution Logs</h4>
          <div className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-auto max-h-96 font-mono text-sm whitespace-pre-wrap">
            {currentRun.logs || 'No logs available yet...'}
          </div>
        </div>

        {currentRun.outputs && (
          <div>
            <h4 className="font-semibold mb-2">Output</h4>
            <div className="bg-white p-4 border border-gray-200 rounded-lg">
              {currentRun.outputs.final_output ? (
                <div className="prose max-w-none">
                  <pre className="whitespace-pre-wrap text-sm">{currentRun.outputs.final_output}</pre>
                </div>
              ) : (
                <pre className="text-sm text-gray-600">{JSON.stringify(currentRun.outputs, null, 2)}</pre>
              )}
            </div>
          </div>
        )}

        {currentRun.artifacts && currentRun.artifacts.length > 0 && (
          <div>
            <h4 className="font-semibold mb-2">Artifacts ({currentRun.artifacts.length})</h4>
            <div className="space-y-2">
              {currentRun.artifacts.map((artifact) => (
                <details key={artifact.id} className="border border-gray-200 rounded-lg">
                  <summary className="p-3 cursor-pointer hover:bg-gray-50 font-medium">
                    {artifact.name} ({artifact.type})
                  </summary>
                  <div className="p-4 bg-gray-50 border-t border-gray-200">
                    <pre className="text-sm whitespace-pre-wrap">{artifact.content}</pre>
                  </div>
                </details>
              ))}
            </div>
          </div>
        )}

        {currentRun.error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
            <h4 className="font-semibold text-red-900 mb-2">Error:</h4>
            <p className="text-sm text-red-800">{currentRun.error}</p>
          </div>
        )}
      </div>
    )
  }

  const renderFilesTab = () => {
    if (!agent?.repo_url) {
      return (
        <div className="text-center py-8">
          <p className="text-gray-600 mb-4">
            This agent doesn't have a GitHub repository yet.
          </p>
          <button
            onClick={handleCreateRepo}
            disabled={creatingRepo}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {creatingRepo ? 'Creating Repository...' : 'Create GitHub Repository'}
          </button>
        </div>
      )
    }

    return (
      <div className="grid grid-cols-3 gap-4">
        {/* File List */}
        <div className="col-span-1 border-r border-gray-200 pr-4">
          <div className="mb-4">
            <a
              href={agent.repo_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 0C4.477 0 0 4.484 0 10.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0110 4.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.203 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.942.359.31.678.921.678 1.856 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0020 10.017C20 4.484 15.522 0 10 0z" clipRule="evenodd" />
              </svg>
              Open on GitHub →
            </a>
          </div>

          <div className="space-y-1">
            {files.length === 0 ? (
              <p className="text-sm text-gray-500">No files found</p>
            ) : (
              files.map((file) => (
                <button
                  key={file.path}
                  onClick={() => setSelectedFile(file)}
                  className={`w-full text-left px-2 py-1 text-sm rounded hover:bg-gray-100 ${
                    selectedFile?.path === file.path ? 'bg-blue-50 text-blue-700' : 'text-gray-700'
                  }`}
                >
                  📄 {file.name}
                </button>
              ))
            )}
          </div>
        </div>

        {/* File Content */}
        <div className="col-span-2">
          {selectedFile ? (
            <div>
              <div className="mb-2 flex justify-between items-center">
                <h4 className="font-semibold text-gray-900">{selectedFile.path}</h4>
                <span className="text-xs text-gray-500">
                  {(selectedFile.size / 1024).toFixed(1)} KB
                </span>
              </div>
              <div className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-auto max-h-[600px]">
                <pre className="text-sm">{selectedFile.content}</pre>
              </div>
            </div>
          ) : (
            <div className="text-center text-gray-500 py-8">
              Select a file to view its contents
            </div>
          )}
        </div>
      </div>
    )
  }

  const renderMemoryTab = () => {
    if (!currentRun?.recalled_memory) {
      return (
        <div className="text-center text-gray-500 py-8">
          No memory data available. Run the agent first.
        </div>
      )
    }

    const memories = currentRun.recalled_memory.items || []

    return (
      <div className="space-y-4">
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <p className="text-sm text-blue-900">
            <strong>Recalled {currentRun.recalled_memory.count || 0} memories</strong> from past executions to provide context.
          </p>
        </div>

        {memories.length === 0 ? (
          <div className="text-center text-gray-500 py-8">
            No relevant memories found for this execution.
          </div>
        ) : (
          <div className="space-y-3">
            {memories.map((memory: any, index: number) => (
              <div key={memory.id || index} className="p-4 border border-gray-200 rounded-lg">
                <div className="flex justify-between items-start mb-2">
                  <span className="text-xs font-semibold text-gray-500">
                    Memory #{index + 1}
                  </span>
                  <span className="text-xs px-2 py-1 bg-green-100 text-green-800 rounded">
                    Relevance: {(memory.relevance_score * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-sm text-gray-700">{memory.text}</p>
                {memory.metadata && (
                  <div className="mt-2 text-xs text-gray-500">
                    <code>{JSON.stringify(memory.metadata)}</code>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  const renderCodeTab = () => {
    if (!agent) return null

    return (
      <div className="space-y-4">
        <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
          <h4 className="font-semibold mb-2">Agent Specification</h4>
          <p className="text-sm text-gray-600 mb-4">
            This is the underlying configuration for this agent. It defines the workflow, tools, and capabilities.
          </p>
        </div>

        <div className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-auto max-h-[600px]">
          <pre className="text-sm">
            {JSON.stringify(agent.agent_spec, null, 2)}
          </pre>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-gray-600">Loading agent...</p>
        </div>
      </div>
    )
  }

  if (!agent) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-800 mb-2">Agent Not Found</h2>
          <p className="text-gray-600">The agent you're looking for doesn't exist.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* API Key Modal */}
      <ApiKeyModal
        isOpen={showKeyModal}
        missingKeys={missingKeys}
        onClose={() => setShowKeyModal(false)}
        onSuccess={handleKeysSuccess}
      />

      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2">{agent.name}</h1>
              {agent.description && (
                <p className="text-gray-600">{agent.description}</p>
              )}
              {agent.repo_url && (
                <div className="mt-2">
                  <a
                    href={agent.repo_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
                  >
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 0C4.477 0 0 4.484 0 10.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0110 4.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.203 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.942.359.31.678.921.678 1.856 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0020 10.017C20 4.484 15.522 0 10 0z" clipRule="evenodd" />
                    </svg>
                    GitHub Repository
                  </a>
                </div>
              )}
            </div>
            <div className="text-right">
              <div className="text-sm text-gray-500">
                <div>Runs: {agent.run_count}</div>
                <div>Success: {agent.success_count}</div>
                <div className="mt-2 text-xs">
                  Created: {new Date(agent.created_at).toLocaleDateString()}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-white rounded-lg shadow-sm">
          <div className="border-b border-gray-200">
            <nav className="flex -mb-px">
              {[
                { id: 'run', label: 'Run Agent' },
                { id: 'logs', label: 'Logs & Results' },
                { id: 'files', label: 'Files' },
                { id: 'memory', label: 'Memory' },
                { id: 'code', label: 'View Code' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as TabType)}
                  className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === tab.id
                      ? 'border-blue-600 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>

          <div className="p-6">
            {activeTab === 'run' && renderRunTab()}
            {activeTab === 'logs' && renderLogsTab()}
            {activeTab === 'files' && renderFilesTab()}
            {activeTab === 'memory' && renderMemoryTab()}
            {activeTab === 'code' && renderCodeTab()}
          </div>
        </div>
      </div>
    </div>
  )
}
