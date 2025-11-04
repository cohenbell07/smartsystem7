'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { getSecrets, updateSecrets } from '@/lib/api'

export default function SettingsPage() {
  const { data, error, mutate } = useSWR('secrets', getSecrets)
  const [secrets, setSecrets] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)

    try {
      await updateSecrets(secrets)
      setSaved(true)
      setSecrets({}) // Clear form
      mutate() // Refresh
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      alert('Failed to save secrets')
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          Failed to load settings
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading settings...</p>
        </div>
      </div>
    )
  }

  const currentSecrets = data.secrets || {}

  const secretFields = [
    { key: 'OPENAI_API_KEY', label: 'OpenAI API Key', placeholder: 'sk-...' },
    { key: 'ANTHROPIC_API_KEY', label: 'Anthropic API Key', placeholder: 'sk-ant-...' },
    { key: 'BING_SEARCH_API_KEY', label: 'Bing Search API Key', placeholder: 'Optional' },
    { key: 'SERPAPI_KEY', label: 'SerpAPI Key', placeholder: 'Optional' },
    { key: 'GITHUB_TOKEN', label: 'GitHub Token', placeholder: 'ghp_...' },
    { key: 'SMTP_USER', label: 'SMTP User (Email)', placeholder: 'you@gmail.com' },
    { key: 'SMTP_PASSWORD', label: 'SMTP Password', placeholder: 'App password' },
    { key: 'DISCORD_WEBHOOK_URL', label: 'Discord Webhook URL', placeholder: 'https://discord.com/api/webhooks/...' },
  ]

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Settings</h1>
        <p className="text-gray-600">
          Configure API keys and integrations
        </p>
      </div>

      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
        <h3 className="font-medium text-yellow-900 mb-1">Note</h3>
        <p className="text-sm text-yellow-700">
          Secrets are stored server-side and redacted in logs. In production, use proper encryption.
        </p>
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-6">API Keys</h2>

        <div className="space-y-6">
          {secretFields.map(({ key, label, placeholder }) => (
            <div key={key}>
              <label htmlFor={key} className="block text-sm font-medium text-gray-700 mb-2">
                {label}
              </label>
              <div className="flex gap-3">
                <input
                  id={key}
                  type="password"
                  placeholder={currentSecrets[key] || placeholder}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                  value={secrets[key] || ''}
                  onChange={(e) => setSecrets({ ...secrets, [key]: e.target.value })}
                />
                {currentSecrets[key] && (
                  <div className="flex items-center px-3 py-2 bg-green-50 text-green-700 text-sm rounded-lg">
                    ✓ Set
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-8 pt-6 border-t flex items-center justify-between">
          <div className="text-sm text-gray-500">
            {saved && (
              <span className="text-green-600">✓ Secrets saved successfully</span>
            )}
          </div>
          <button
            onClick={handleSave}
            disabled={saving || Object.keys(secrets).length === 0}
            className="px-6 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>

      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 className="font-medium text-blue-900 mb-2">Getting API Keys</h3>
        <ul className="text-sm text-blue-700 space-y-1">
          <li>
            <strong>OpenAI:</strong> <a href="https://platform.openai.com/api-keys" target="_blank" className="underline">platform.openai.com/api-keys</a>
          </li>
          <li>
            <strong>Anthropic:</strong> <a href="https://console.anthropic.com/" target="_blank" className="underline">console.anthropic.com</a>
          </li>
          <li>
            <strong>Bing Search:</strong> <a href="https://azure.microsoft.com/en-us/services/cognitive-services/bing-web-search-api/" target="_blank" className="underline">Azure Portal</a>
          </li>
          <li>
            <strong>GitHub:</strong> Settings → Developer settings → Personal access tokens
          </li>
        </ul>
      </div>
    </div>
  )
}
