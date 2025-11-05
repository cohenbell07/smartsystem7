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

  const secretGroups = [
    {
      title: 'AI Models',
      description: 'At least one is required for agent execution',
      fields: [
        {
          key: 'OPENAI_API_KEY',
          label: 'OpenAI API Key',
          placeholder: 'sk-...',
          required: false,
          url: 'https://platform.openai.com/api-keys'
        },
        {
          key: 'ANTHROPIC_API_KEY',
          label: 'Anthropic API Key',
          placeholder: 'sk-ant-...',
          required: false,
          url: 'https://console.anthropic.com/settings/keys'
        },
      ]
    },
    {
      title: 'Version Control & Code',
      description: 'Required for CodeArchitect and GitHub operations',
      fields: [
        {
          key: 'GITHUB_TOKEN',
          label: 'GitHub Personal Access Token',
          placeholder: 'ghp_...',
          required: false,
          url: 'https://github.com/settings/tokens'
        },
      ]
    },
    {
      title: 'Web Search',
      description: 'Recommended for research agents',
      fields: [
        {
          key: 'SERPAPI_KEY',
          label: 'SerpAPI Key (Recommended)',
          placeholder: 'Optional',
          required: false,
          url: 'https://serpapi.com/manage-api-key'
        },
        {
          key: 'BING_SEARCH_API_KEY',
          label: 'Bing Search API Key',
          placeholder: 'Optional',
          required: false,
          url: 'https://www.microsoft.com/en-us/bing/apis/bing-web-search-api'
        },
      ]
    },
    {
      title: 'Notifications',
      description: 'Optional - for email and Discord notifications',
      fields: [
        {
          key: 'SMTP_USER',
          label: 'SMTP User (Email)',
          placeholder: 'you@gmail.com',
          required: false,
          url: 'https://support.google.com/mail/answer/185833'
        },
        {
          key: 'SMTP_PASSWORD',
          label: 'SMTP Password (App Password)',
          placeholder: 'App password',
          required: false,
          url: 'https://support.google.com/mail/answer/185833'
        },
        {
          key: 'DISCORD_WEBHOOK_URL',
          label: 'Discord Webhook URL',
          placeholder: 'https://discord.com/api/webhooks/...',
          required: false,
          url: 'https://support.discord.com/hc/en-us/articles/228383668'
        },
      ]
    }
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

      <div className="space-y-6">
        {secretGroups.map((group) => (
          <div key={group.title} className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-2">{group.title}</h2>
            <p className="text-sm text-gray-600 mb-6">{group.description}</p>

            <div className="space-y-5">
              {group.fields.map(({ key, label, placeholder, url }) => (
                <div key={key}>
                  <label htmlFor={key} className="block text-sm font-medium text-gray-700 mb-2">
                    {label}
                  </label>
                  <div className="flex gap-2">
                    <input
                      id={key}
                      type="password"
                      placeholder={currentSecrets[key] || placeholder}
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                      value={secrets[key] || ''}
                      onChange={(e) => setSecrets({ ...secrets, [key]: e.target.value })}
                    />
                    {currentSecrets[key] ? (
                      <div className="flex items-center px-3 py-2 bg-green-50 text-green-700 text-sm rounded-lg whitespace-nowrap">
                        ✓ Configured
                      </div>
                    ) : (
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center px-3 py-2 bg-blue-50 text-blue-700 text-sm rounded-lg hover:bg-blue-100 transition-colors whitespace-nowrap"
                      >
                        Get Key →
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-500">
            {saved && (
              <span className="text-green-600 font-medium">✓ API keys saved successfully</span>
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
    </div>
  )
}
