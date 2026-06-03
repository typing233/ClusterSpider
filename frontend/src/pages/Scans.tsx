import { useState, useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { createScan, getScan } from '../api/scans'

interface ScanJob {
  task_id: string
  target: string
  target_type: string
  status: string
  progress?: { total: number; completed: number; current_module: string }
}

export default function ScansPage() {
  const [target, setTarget] = useState('')
  const [targetType, setTargetType] = useState('domain')
  const [scans, setScans] = useState<ScanJob[]>([])

  const scanMutation = useMutation({
    mutationFn: () => createScan(target, targetType),
    onSuccess: (data) => {
      const job: ScanJob = { ...data, status: 'PENDING' }
      setScans((prev) => [job, ...prev])
      setTarget('')
      startSSE(data.task_id)
    },
  })

  const startSSE = (taskId: string) => {
    const token = localStorage.getItem('clusterspider-auth')
    const eventSource = new EventSource(`/api/v1/scans/${taskId}/stream`)

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setScans((prev) =>
          prev.map((s) =>
            s.task_id === taskId
              ? { ...s, status: data.state, progress: data }
              : s
          )
        )
        if (data.state === 'COMPLETED' || data.state === 'FAILED') {
          eventSource.close()
        }
      } catch {}
    }

    eventSource.onerror = () => {
      eventSource.close()
    }
  }

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-white mb-6">Scans</h2>

      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 mb-6">
        <h3 className="text-lg font-semibold text-white mb-4">New Scan</h3>
        <div className="flex gap-3">
          <input
            type="text"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="Enter target (domain, IP, email...)"
            className="flex-1 px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-cyan-500"
          />
          <select
            value={targetType}
            onChange={(e) => setTargetType(e.target.value)}
            className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white"
          >
            <option value="domain">Domain</option>
            <option value="ip">IP</option>
            <option value="email">Email</option>
            <option value="username">Username</option>
          </select>
          <button
            onClick={() => scanMutation.mutate()}
            disabled={!target || scanMutation.isPending}
            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg font-medium disabled:opacity-50 transition-colors"
          >
            {scanMutation.isPending ? 'Starting...' : 'Start Scan'}
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {scans.map((scan) => (
          <div
            key={scan.task_id}
            className="bg-slate-800 border border-slate-700 rounded-lg p-4"
          >
            <div className="flex items-center justify-between mb-2">
              <div>
                <span className="text-white font-medium">{scan.target}</span>
                <span className="text-slate-400 text-sm ml-2">({scan.target_type})</span>
              </div>
              <span
                className={`px-2 py-1 rounded text-xs font-medium ${
                  scan.status === 'COMPLETED'
                    ? 'bg-green-500/20 text-green-400'
                    : scan.status === 'FAILED'
                    ? 'bg-red-500/20 text-red-400'
                    : scan.status === 'PROGRESS'
                    ? 'bg-yellow-500/20 text-yellow-400'
                    : 'bg-slate-600/50 text-slate-300'
                }`}
              >
                {scan.status}
              </span>
            </div>

            {scan.progress && scan.status === 'PROGRESS' && (
              <div>
                <div className="flex justify-between text-xs text-slate-400 mb-1">
                  <span>Module: {scan.progress.current_module}</span>
                  <span>
                    {scan.progress.completed}/{scan.progress.total}
                  </span>
                </div>
                <div className="w-full h-2 bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-cyan-500 rounded-full transition-all duration-300"
                    style={{
                      width: `${(scan.progress.completed / scan.progress.total) * 100}%`,
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        ))}

        {scans.length === 0 && (
          <div className="text-center text-slate-500 py-8">
            No scans yet. Start a new scan above.
          </div>
        )}
      </div>
    </div>
  )
}
