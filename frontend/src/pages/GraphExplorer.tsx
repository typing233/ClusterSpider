import { useState, useCallback, useRef } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { useGraphStore, GraphNode } from '../store/graph'
import { getNeighbors, searchNodes } from '../api/graph'

const NODE_COLORS: Record<string, string> = {
  Domain: '#06b6d4',
  IP: '#22c55e',
  Email: '#f59e0b',
  Username: '#a855f7',
  Certificate: '#ec4899',
  Organization: '#3b82f6',
  LeakRecord: '#ef4444',
}

export default function GraphExplorerPage() {
  const { nodes, edges, selectedNode, setGraphData, selectNode } = useGraphStore()
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [depth, setDepth] = useState(2)
  const graphRef = useRef<any>(null)

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    const res = await searchNodes(searchQuery)
    setSearchResults(res.results || [])
  }

  const handleLoadNode = async (entityType: string, value: string) => {
    const data = await getNeighbors(entityType, value, depth)
    if (data.nodes) {
      const graphNodes = data.nodes.map((n: any) => ({
        id: n._id,
        ...n,
        color: NODE_COLORS[n._label] || '#94a3b8',
      }))
      const graphEdges = (data.edges || []).map((e: any) => ({
        source: e.source,
        target: e.target,
        label: e.type,
      }))
      setGraphData(graphNodes, graphEdges)
    }
    setSearchResults([])
  }

  const handleNodeClick = useCallback(
    (node: any) => {
      selectNode(node)
    },
    [selectNode]
  )

  const handleNodeDblClick = useCallback(
    async (node: any) => {
      const label = node._label?.toLowerCase() || 'domain'
      const value = node.value || node.name || node.fingerprint || node.breach_name
      if (value) {
        await handleLoadNode(label, value)
      }
    },
    [depth]
  )

  const graphData = {
    nodes: nodes.map((n) => ({ ...n, id: n._id, color: NODE_COLORS[n._label] || '#94a3b8' })),
    links: edges.map((e) => ({ ...e, source: e.source, target: e.target })),
  }

  return (
    <div className="flex h-full">
      <div className="w-80 bg-slate-800 border-r border-slate-700 p-4 overflow-y-auto">
        <h3 className="text-lg font-semibold text-white mb-4">Search</h3>

        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search entities..."
            className="flex-1 px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-sm text-white focus:outline-none focus:border-cyan-500"
          />
          <button
            onClick={handleSearch}
            className="px-3 py-2 bg-cyan-600 text-white rounded-lg text-sm hover:bg-cyan-500"
          >
            Go
          </button>
        </div>

        <div className="mb-4">
          <label className="block text-xs text-slate-400 mb-1">Depth: {depth}</label>
          <input
            type="range"
            min={1}
            max={5}
            value={depth}
            onChange={(e) => setDepth(Number(e.target.value))}
            className="w-full"
          />
        </div>

        {searchResults.length > 0 && (
          <div className="space-y-2 mb-4">
            <h4 className="text-sm text-slate-400">Results</h4>
            {searchResults.map((r: any, i: number) => (
              <button
                key={i}
                onClick={() => handleLoadNode(r._label?.toLowerCase(), r.value || r.name)}
                className="w-full text-left px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded text-sm"
              >
                <span
                  className="inline-block w-2 h-2 rounded-full mr-2"
                  style={{ backgroundColor: NODE_COLORS[r._label] || '#94a3b8' }}
                />
                <span className="text-white">{r.value || r.name || r.fingerprint}</span>
                <span className="text-slate-400 ml-2 text-xs">{r._label}</span>
              </button>
            ))}
          </div>
        )}

        <div className="mb-4">
          <h4 className="text-sm text-slate-400 mb-2">Legend</h4>
          <div className="space-y-1">
            {Object.entries(NODE_COLORS).map(([label, color]) => (
              <div key={label} className="flex items-center gap-2 text-xs text-slate-300">
                <span className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                {label}
              </div>
            ))}
          </div>
        </div>

        {selectedNode && (
          <div className="mt-4 p-3 bg-slate-700 rounded-lg">
            <h4 className="text-sm font-medium text-white mb-2">
              {selectedNode._label}
            </h4>
            <div className="space-y-1 text-xs text-slate-300">
              {Object.entries(selectedNode)
                .filter(([k]) => !k.startsWith('_') && k !== 'color' && k !== 'x' && k !== 'y' && k !== 'vx' && k !== 'vy' && k !== 'index' && k !== 'id')
                .map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-slate-400">{k}:</span>
                    <span className="truncate ml-2 max-w-[150px]">{String(v)}</span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex-1 relative">
        {nodes.length > 0 ? (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            nodeLabel={(node: any) => `${node._label}: ${node.value || node.name || ''}`}
            nodeColor={(node: any) => node.color}
            nodeRelSize={6}
            linkLabel={(link: any) => link.label}
            linkColor={() => '#475569'}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={0.9}
            onNodeClick={handleNodeClick}
            onNodeDragEnd={(node: any) => {
              node.fx = node.x
              node.fy = node.y
            }}
            backgroundColor="#0f172a"
          />
        ) : (
          <div className="flex items-center justify-center h-full text-slate-500">
            <div className="text-center">
              <p className="text-lg mb-2">No graph data loaded</p>
              <p className="text-sm">Search for an entity to explore its relationships</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
