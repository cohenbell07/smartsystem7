'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { askQuestion } from '@/lib/api'

export default function Home() {
  const router = useRouter()
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!question.trim()) {
      setError('Please enter a question')
      return
    }

    setLoading(true)
    setError('')

    try {
      const result = await askQuestion(question)
      router.push(`/projects/${result.project_id}`)
    } catch (err) {
      setError('Failed to submit question. Please try again.')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          Ask a Business Question
        </h1>
        <p className="text-lg text-gray-600">
          I'll research 50+ sources, analyze viability, and design a custom AI agent to help you execute.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label htmlFor="question" className="block text-sm font-medium text-gray-700 mb-2">
            Your Question
          </label>
          <textarea
            id="question"
            rows={6}
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent resize-none"
            placeholder="Example: What's the market viability of an AI-powered meal planning app for busy parents?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={loading}
          />
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-primary text-white py-3 px-6 rounded-lg font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? (
            <span className="flex items-center justify-center">
              <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Researching...
            </span>
          ) : (
            'Start Research'
          )}
        </button>
      </form>

      {/* Example Questions */}
      <div className="mt-12">
        <h2 className="text-sm font-medium text-gray-700 mb-4">Example Questions:</h2>
        <div className="space-y-2">
          {[
            "What's the viability of a SaaS tool for freelance designers?",
            "How competitive is the online tutoring market for K-12 students?",
            "Should I build a mobile app for local restaurant discovery?",
            "What's the market potential for AI-powered code review tools?",
          ].map((example, i) => (
            <button
              key={i}
              onClick={() => setQuestion(example)}
              className="block w-full text-left px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-md transition-colors"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
