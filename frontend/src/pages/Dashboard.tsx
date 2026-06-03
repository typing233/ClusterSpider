import { useQuery } from '@tanstack/react-query'
import { getGraphStats } from '../api/graph'

export default function DashboardPage() {
  const { data: stats } = useQuery({
    queryKey: ['graphStats'],
    queryFn: getGraphStats,
  })

  const statCards = stats
    ? Object.entries(stats)
        .filter(([key]) => key !== '_relationships')
        .map(([label, count]) => ({ label, count: count as number }))
    : []

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-white mb-6">Dashboard</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {statCards.map((stat) => (
          <div
            key={stat.label}
            className="bg-slate-800 border border-slate-700 rounded-lg p-4"
          >
            <div className="text-3xl font-bold text-cyan-400">{stat.count}</div>
            <div className="text-sm text-slate-400 mt-1">{stat.label}s</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h3 className="text-lg font-semibold text-white mb-4">Relationships</h3>
          {stats?._relationships && (
            <div className="space-y-2">
              {Object.entries(stats._relationships as Record<string, number>).map(
                ([type, count]) => (
                  <div key={type} className="flex justify-between text-sm">
                    <span className="text-slate-300">{type}</span>
                    <span className="text-cyan-400 font-mono">{count}</span>
                  </div>
                )
              )}
            </div>
          )}
        </div>

        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h3 className="text-lg font-semibold text-white mb-4">Quick Actions</h3>
          <div className="space-y-2">
            <a
              href="/scans"
              className="block px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-slate-200 transition-colors"
            >
              New Scan
            </a>
            <a
              href="/graph"
              className="block px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-slate-200 transition-colors"
            >
              Explore Graph
            </a>
            <a
              href="/reports"
              className="block px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-slate-200 transition-colors"
            >
              Generate Report
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
