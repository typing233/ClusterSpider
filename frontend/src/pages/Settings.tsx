import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'

export default function SettingsPage() {
  const [serviceName, setServiceName] = useState('')
  const [apiKey, setApiKey] = useState('')
  const queryClient = useQueryClient()

  const { data: keys } = useQuery({
    queryKey: ['apiKeys'],
    queryFn: async () => {
      const res = await api.get('/users/me/api-keys')
      return res.data
    },
  })

  const addKeyMutation = useMutation({
    mutationFn: async () => {
      await api.post('/users/me/api-keys', {
        service_name: serviceName,
        api_key: apiKey,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apiKeys'] })
      setServiceName('')
      setApiKey('')
    },
  })

  const deleteKeyMutation = useMutation({
    mutationFn: async (keyId: string) => {
      await api.delete(`/users/me/api-keys/${keyId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apiKeys'] })
    },
  })

  return (
    <div className="p-6 max-w-2xl">
      <h2 className="text-2xl font-bold text-white mb-6">Settings</h2>

      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 mb-6">
        <h3 className="text-lg font-semibold text-white mb-4">API Key Management</h3>
        <p className="text-sm text-slate-400 mb-4">
          Add API keys for third-party data sources. Keys are stored encrypted.
        </p>

        <div className="flex gap-3 mb-4">
          <select
            value={serviceName}
            onChange={(e) => setServiceName(e.target.value)}
            className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white"
          >
            <option value="">Select service...</option>
            <option value="hibp">Have I Been Pwned</option>
            <option value="github">GitHub</option>
            <option value="ipinfo">IPinfo</option>
            <option value="shodan">Shodan</option>
          </select>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="API Key"
            className="flex-1 px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-cyan-500"
          />
          <button
            onClick={() => addKeyMutation.mutate()}
            disabled={!serviceName || !apiKey}
            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm disabled:opacity-50"
          >
            Add
          </button>
        </div>

        <div className="space-y-2">
          {(keys || []).map((key: any) => (
            <div
              key={key.id}
              className="flex items-center justify-between px-3 py-2 bg-slate-700 rounded-lg"
            >
              <div>
                <span className="text-white text-sm">{key.service_name}</span>
                <span className="text-slate-400 text-xs ml-2">Added: {key.created_at}</span>
              </div>
              <button
                onClick={() => deleteKeyMutation.mutate(key.id)}
                className="text-red-400 hover:text-red-300 text-sm"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
