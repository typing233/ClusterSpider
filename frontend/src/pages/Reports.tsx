import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { createReport, getReport } from '../api/scans'

interface ReportJob {
  task_id: string
  target: string
  format: string
  status: string
  download_path?: string
}

export default function ReportsPage() {
  const [target, setTarget] = useState('')
  const [targetType, setTargetType] = useState('domain')
  const [format, setFormat] = useState('html')
  const [reports, setReports] = useState<ReportJob[]>([])

  const reportMutation = useMutation({
    mutationFn: () => createReport(target, targetType, format),
    onSuccess: (data) => {
      const job: ReportJob = { task_id: data.task_id, target, format, status: 'PENDING' }
      setReports((prev) => [job, ...prev])
      setTarget('')
      pollReport(data.task_id)
    },
  })

  const pollReport = async (taskId: string) => {
    const interval = setInterval(async () => {
      try {
        const data = await getReport(taskId)
        if (data.status === 'SUCCESS') {
          setReports((prev) =>
            prev.map((r) =>
              r.task_id === taskId
                ? { ...r, status: 'COMPLETED', download_path: data.result?.path }
                : r
            )
          )
          clearInterval(interval)
        } else if (data.status === 'FAILURE') {
          setReports((prev) =>
            prev.map((r) => (r.task_id === taskId ? { ...r, status: 'FAILED' } : r))
          )
          clearInterval(interval)
        }
      } catch {
        clearInterval(interval)
      }
    }, 3000)
  }

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-white mb-6">Reports</h2>

      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 mb-6">
        <h3 className="text-lg font-semibold text-white mb-4">Generate Report</h3>
        <div className="flex gap-3">
          <input
            type="text"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="Enter target..."
            className="flex-1 px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-cyan-500"
          />
          <select
            value={targetType}
            onChange={(e) => setTargetType(e.target.value)}
            className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white"
          >
            <option value="domain">Domain</option>
            <option value="ip">IP</option>
          </select>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white"
          >
            <option value="html">HTML</option>
            <option value="pdf">PDF</option>
          </select>
          <button
            onClick={() => reportMutation.mutate()}
            disabled={!target || reportMutation.isPending}
            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg font-medium disabled:opacity-50 transition-colors"
          >
            Generate
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {reports.map((report) => (
          <div
            key={report.task_id}
            className="bg-slate-800 border border-slate-700 rounded-lg p-4 flex items-center justify-between"
          >
            <div>
              <span className="text-white font-medium">{report.target}</span>
              <span className="text-slate-400 text-sm ml-2">({report.format.toUpperCase()})</span>
            </div>
            <div className="flex items-center gap-3">
              <span
                className={`px-2 py-1 rounded text-xs font-medium ${
                  report.status === 'COMPLETED'
                    ? 'bg-green-500/20 text-green-400'
                    : report.status === 'FAILED'
                    ? 'bg-red-500/20 text-red-400'
                    : 'bg-slate-600/50 text-slate-300'
                }`}
              >
                {report.status}
              </span>
              {report.status === 'COMPLETED' && (
                <a
                  href={`/api/v1/reports/${report.task_id}/download`}
                  className="px-3 py-1 bg-cyan-600 hover:bg-cyan-500 text-white rounded text-xs"
                >
                  Download
                </a>
              )}
            </div>
          </div>
        ))}

        {reports.length === 0 && (
          <div className="text-center text-slate-500 py-8">
            No reports generated yet.
          </div>
        )}
      </div>
    </div>
  )
}
