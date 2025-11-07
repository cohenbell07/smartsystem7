'use client'

import { useState } from 'react'
import { setKeys } from '@/lib/api'

interface MissingKey {
  key: string
  url: string
  description: string
}

interface ApiKeyModalProps {
  isOpen: boolean
  missingKeys: MissingKey[]
  onClose: () => void
  onSuccess: () => void
}

export default function ApiKeyModal({
  isOpen,
  missingKeys,
  onClose,
  onSuccess,
}: ApiKeyModalProps) {
  const [keys, setKeysState] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      // Filter out empty keys
      const nonEmptyKeys = Object.entries(keys).reduce((acc, [key, value]) => {
        if (value && value.trim()) {
          acc[key] = value.trim()
        }
        return acc
      }, {} as Record<string, string>)

      if (Object.keys(nonEmptyKeys).length === 0) {
        setError('Please provide at least one API key')
        setLoading(false)
        return
      }

      await setKeys(nonEmptyKeys)
      onSuccess()
    } catch (err: any) {
      setError(err.message || 'Failed to save API keys')
      setLoading(false)
    }
  }

  const handleKeyChange = (key: string, value: string) => {
    setKeysState((prev) => ({
      ...prev,
      [key]: value,
    }))
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <h2 className="text-2xl font-bold mb-4">Required API Keys</h2>

          <p className="text-gray-600 mb-6">
            This agent requires the following API keys to run. Please provide
            them below:
          </p>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="space-y-4">
              {missingKeys.map((missing) => (
                <div key={missing.key} className="border rounded-lg p-4">
                  <label className="block">
                    <div className="flex justify-between items-start mb-2">
                      <span className="font-semibold text-gray-900">
                        {missing.key}
                      </span>
                      {missing.url && (
                        <a
                          href={missing.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-blue-600 hover:text-blue-800 underline"
                        >
                          Get key →
                        </a>
                      )}
                    </div>
                    {missing.description && (
                      <p className="text-sm text-gray-600 mb-2">
                        {missing.description}
                      </p>
                    )}
                    <input
                      type="password"
                      value={keys[missing.key] || ''}
                      onChange={(e) =>
                        handleKeyChange(missing.key, e.target.value)
                      }
                      placeholder={`Enter your ${missing.key}`}
                      className="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </label>
                </div>
              ))}
            </div>

            <div className="mt-6 flex justify-end space-x-3">
              <button
                type="button"
                onClick={onClose}
                disabled={loading}
                className="px-4 py-2 text-gray-700 bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 flex items-center"
              >
                {loading ? (
                  <>
                    <svg
                      className="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      ></circle>
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      ></path>
                    </svg>
                    Saving...
                  </>
                ) : (
                  'Save & Continue'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
