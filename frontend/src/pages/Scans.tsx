import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createScan, listScans } from '../api/scans'
import { useAuthStore } from '../store/auth'

interface ScanJob {
  id: string
  task_id: string
  target: string
  target_type: string
  status: string
  modules_total: number
  modules_completed: number
  created_at: string
  finished_at: string | null
  progress?: { total: number; completed: number; current_module: string; state?: string }
}

export default function ScansPage() {
  const [target, setTarget] = useState('')
  const [targetType, setTargetType] = useState('domain')
  const [liveProgress, setLiveProgress] = useState<Record<string, any>>({})
  const queryClient = useQueryClient()
  const accessToken = useAuthStore((s) => s.accessToken)

  const { data: scanHistory = [] } = useQuery<ScanJob[]>({
    queryKey: ['scanHistory'],
    queryFn: () => listScans(),
    refetchInterval: 10000,
  })

  const scanMutation = useMutation({
    mutationFn: () => createScan(target, targetType),
    onSuccess: (data) => {
      setTarget('')
      queryClient.invalidateQueries({ queryKey: ['scanHistory'] })
      startSSE(data.task_id)
    },
  })

  const startSSE = (taskId: string) => {
    if (!accessToken) return
    // Pass token as query param since EventSource cannot set Authorization header
    const url = `/api/v1/scans/${taskId}/stream?token=${encodeURIComponent(accessToken)}`
    const eventSource = new EventSource(url)

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setLiveProgress((prev) => ({ ...prev, [taskId]: data }))

        if (data.state === 'COMPLETED' || data.state === 'FAILED') {
          eventSource.close()
          queryClient.invalidateQueries({ queryKey: ['scanHistory'] })
          setTimeout(() => {
            setLiveProgress((prev) => {
              const copy = { ...prev }
              delete copy[taskId]
              return copy
            })
          }, 2000)
        }
      } catch { /* ignore parse errors */ }
    }

    eventSource.onerror = () => {
      eventSource.close()
    }
  }

  // Resume SSE for any scan that's still running when page loads
  useEffect(() => {
    scanHistory.forEach((scan) => {
      if (scan.status === 'STARTED' || scan.status === 'PROGRESS' || scan.status === 'PENDING') {
        if (!liveProgress[scan.task_id]) {
          startSSE(scan.task_id)
        }
      }
    })
  }, [scanHistory])

  const getDisplayStatus = (scan: ScanJob) => {
    const live = liveProgress[scan.task_id]
    if (live) return live.state || scan.status
    return scan.status
  }

  const getProgress = (scan: ScanJob) => {
    return liveProgress[scan.task_id] || null
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
            onKeyDown={(e) => e.key === 'Enter' && target && scanMutation.mutate()}
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

      <h3 className="text-lg font-semibold text-white mb-3">Scan History</h3>
      <div className="space-y-3">
        {scanHistory.map((scan) => {
          const status = getDisplayStatus(scan)
          const progress = getProgress(scan)
          return (
            <div
              key={scan.task_id}
              className="bg-slate-800 border border-slate-700 rounded-lg p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="text-white font-medium">{scan.target}</span>
                  <span className="text-slate-400 text-sm ml-2">({scan.target_type})</span>
                  <span className="text-slate-500 text-xs ml-3">
                    {new Date(scan.created_at).toLocaleString()}
                  </span>
                </div>
                <span
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    status === 'COMPLETED'
                      ? 'bg-green-500/20 text-green-400'
                      : status === 'FAILED'
                      ? 'bg-red-500/20 text-red-400'
                      : status === 'PROGRESS' || status === 'STARTED'
                      ? 'bg-yellow-500/20 text-yellow-400'
                      : status === 'CANCELLED'
                      ? 'bg-orange-500/20 text-orange-400'
                      : 'bg-slate-600/50 text-slate-300'
                  }`}
                >
                  {status}
                </span>
              </div>

              {progress && (status === 'PROGRESS' || status === 'STARTED') && (
                <div>
                  <div className="flex justify-between text-xs text-slate-400 mb-1">
                    <span>Module: {progress.current_module || 'initializing...'}</span>
                    <span>
                      {progress.completed}/{progress.total}
                    </span>
                  </div>
                  <div className="w-full h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-cyan-500 rounded-full transition-all duration-300"
                      style={{
                        width: progress.total > 0
                          ? `${(progress.completed / progress.total) * 100}%`
                          : '0%',
                      }}
                    />
                  </div>
                </div>
              )}

              {status === 'COMPLETED' && scan.modules_total > 0 && !progress && (
                <div className="text-xs text-slate-400">
                  Completed {scan.modules_completed}/{scan.modules_total} modules
                </div>
              )}
            </div>
          )
        })}

        {scanHistory.length === 0 && (
          <div className="text-center text-slate-500 py-8">
            No scans yet. Start a new scan above.
          </div>
        )}
      </div>
    </div>
  )
}
