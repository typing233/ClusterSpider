import { useState, useCallback, useRef, useMemo } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { useGraphStore } from '../store/graph'
import { getNeighbors, searchNodes, getShortestPath } from '../api/graph'

const NODE_COLORS: Record<string, string> = {
  Domain: '#06b6d4',
  IP: '#22c55e',
  Email: '#f59e0b',
  Username: '#a855f7',
  Certificate: '#ec4899',
  Organization: '#3b82f6',
  LeakRecord: '#ef4444',
  Port: '#64748b',
}

// Mapping from Neo4j label (PascalCase) to API entity_type parameter
const LABEL_TO_API_TYPE: Record<string, string> = {
  Domain: 'domain',
  IP: 'ip',
  Email: 'email',
  Username: 'username',
  Certificate: 'certificate',
  Organization: 'organization',
  LeakRecord: 'leakrecord',
  Port: 'port',
}

const ALL_REL_TYPES = [
  'RESOLVES_TO', 'HAS_SUBDOMAIN', 'REGISTERED_BY', 'BELONGS_TO_ORG',
  'ISSUED_TO', 'APPEARS_IN', 'HAS_USERNAME', 'BELONGS_TO_ASN',
  'REVERSE_DNS', 'NAMESERVER', 'MAIL_EXCHANGE', 'FOUND_IN_REPO',
  'HAS_PORT',
]

const ALL_NODE_TYPES = Object.keys(NODE_COLORS)

export default function GraphExplorerPage() {
  const { nodes, edges, selectedNode, setGraphData, selectNode } = useGraphStore()
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [depth, setDepth] = useState(2)
  const [activeRelTypes, setActiveRelTypes] = useState<Set<string>>(new Set(ALL_REL_TYPES))
  const [activeNodeTypes, setActiveNodeTypes] = useState<Set<string>>(new Set(ALL_NODE_TYPES))
  const [pathMode, setPathMode] = useState(false)
  const [pathFrom, setPathFrom] = useState({ type: 'domain', value: '' })
  const [pathTo, setPathTo] = useState({ type: 'domain', value: '' })
  const [highlightedPath, setHighlightedPath] = useState<Set<string>>(new Set())
  const [highlightedNodes, setHighlightedNodes] = useState<Set<string>>(new Set())
  const graphRef = useRef<any>(null)

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    const res = await searchNodes(searchQuery)
    setSearchResults(res.results || [])
  }

  const handleLoadNode = async (entityType: string, value: string) => {
    // Normalize: accept both Neo4j label ("LeakRecord") and API type ("leakrecord"/"leak")
    const apiType = LABEL_TO_API_TYPE[entityType] || entityType.toLowerCase()
    const relFilter = activeRelTypes.size < ALL_REL_TYPES.length
      ? Array.from(activeRelTypes)
      : undefined
    const data = await getNeighbors(apiType, value, depth, relFilter)
    if (data.nodes) {
      const graphNodes = data.nodes.map((n: any) => ({
        id: n._id,
        ...n,
        color: NODE_COLORS[n._label] || '#94a3b8',
      }))
      const graphEdges = (data.edges || []).map((e: any) => ({
        source: e.source,
        target: e.target,
        type: e.type,
        properties: e.properties || {},
      }))
      setGraphData(graphNodes, graphEdges)
    }
    setSearchResults([])
    setHighlightedPath(new Set())
    setHighlightedNodes(new Set())
  }

  const handleFindPath = async () => {
    if (!pathFrom.value || !pathTo.value) return
    const data = await getShortestPath(pathFrom.type, pathFrom.value, pathTo.type, pathTo.value)
    if (data.nodes && data.nodes.length > 0) {
      const graphNodes = data.nodes.map((n: any) => ({
        id: n._id,
        ...n,
        color: NODE_COLORS[n._label] || '#94a3b8',
      }))
      const graphEdges = (data.edges || []).map((e: any) => ({
        source: e.source,
        target: e.target,
        type: e.type,
        properties: e.properties || {},
      }))
      setGraphData(graphNodes, graphEdges)

      // Highlight the path
      const pathNodeIds = new Set<string>(graphNodes.map((n: any) => n.id))
      const pathEdgeKeys = new Set<string>(graphEdges.map((e: any) => `${e.source}->${e.target}`))
      setHighlightedNodes(pathNodeIds)
      setHighlightedPath(pathEdgeKeys)
    }
  }

  const handleNodeClick = useCallback(
    (node: any) => {
      selectNode(node)
    },
    [selectNode]
  )

  const handleNodeDblClick = useCallback(
    async (node: any) => {
      const label = node._label || 'Domain'
      const value = node.value || node.name || node.fingerprint || node.breach_name
      if (value) {
        await handleLoadNode(label, value)
      }
    },
    [depth, activeRelTypes]
  )

  const toggleRelType = (type: string) => {
    setActiveRelTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  const toggleNodeType = (type: string) => {
    setActiveNodeTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  // Apply node type filter to the graph data
  const filteredGraphData = useMemo(() => {
    const filteredNodes = nodes
      .filter((n) => activeNodeTypes.has(n._label))
      .map((n) => ({
        ...n,
        id: n._id,
        color: highlightedNodes.has(n._id)
          ? '#ffffff'
          : NODE_COLORS[n._label] || '#94a3b8',
        _highlighted: highlightedNodes.has(n._id),
      }))

    const nodeIds = new Set(filteredNodes.map((n) => n.id))
    const filteredEdges = edges
      .filter(
        (e) =>
          activeRelTypes.has(e.type) &&
          nodeIds.has(e.source) &&
          nodeIds.has(e.target)
      )
      .map((e) => ({
        ...e,
        source: e.source,
        target: e.target,
        _highlighted: highlightedPath.has(`${e.source}->${e.target}`),
      }))

    return { nodes: filteredNodes, links: filteredEdges }
  }, [nodes, edges, activeNodeTypes, activeRelTypes, highlightedPath, highlightedNodes])

  return (
    <div className="flex h-full">
      {/* Side panel */}
      <div className="w-80 bg-slate-800 border-r border-slate-700 p-4 overflow-y-auto flex flex-col gap-4">
        {/* Search */}
        <div>
          <h3 className="text-sm font-semibold text-white mb-2">Search Entities</h3>
          <div className="flex gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Search..."
              className="flex-1 px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-white focus:outline-none focus:border-cyan-500"
            />
            <button
              onClick={handleSearch}
              className="px-3 py-1.5 bg-cyan-600 text-white rounded text-sm hover:bg-cyan-500"
            >
              Go
            </button>
          </div>
          {searchResults.length > 0 && (
            <div className="mt-2 space-y-1 max-h-40 overflow-y-auto">
              {searchResults.map((r: any, i: number) => (
                <button
                  key={i}
                  onClick={() => handleLoadNode(r._label || 'Domain', r.value || r.name || r.fingerprint || r.breach_name)}
                  className="w-full text-left px-2 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-xs"
                >
                  <span
                    className="inline-block w-2 h-2 rounded-full mr-2"
                    style={{ backgroundColor: NODE_COLORS[r._label] || '#94a3b8' }}
                  />
                  <span className="text-white">{r.value || r.name || r.fingerprint}</span>
                  <span className="text-slate-400 ml-1">{r._label}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Depth */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">Traversal Depth: {depth}</label>
          <input
            type="range" min={1} max={5} value={depth}
            onChange={(e) => setDepth(Number(e.target.value))}
            className="w-full"
          />
        </div>

        {/* Shortest Path */}
        <div className="border-t border-slate-700 pt-3">
          <button
            onClick={() => setPathMode(!pathMode)}
            className={`w-full text-left text-sm font-medium px-2 py-1.5 rounded ${
              pathMode ? 'bg-cyan-500/20 text-cyan-400' : 'text-slate-300 hover:bg-slate-700'
            }`}
          >
            {pathMode ? '▾' : '▸'} Shortest Path
          </button>
          {pathMode && (
            <div className="mt-2 space-y-2">
              <div className="flex gap-1">
                <select
                  value={pathFrom.type}
                  onChange={(e) => setPathFrom({ ...pathFrom, type: e.target.value })}
                  className="w-24 px-1 py-1 bg-slate-700 border border-slate-600 rounded text-xs text-white"
                >
                  {ALL_NODE_TYPES.map((t) => (
                    <option key={t} value={LABEL_TO_API_TYPE[t] || t.toLowerCase()}>{t}</option>
                  ))}
                </select>
                <input
                  type="text" value={pathFrom.value}
                  onChange={(e) => setPathFrom({ ...pathFrom, value: e.target.value })}
                  placeholder="From value"
                  className="flex-1 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-xs text-white"
                />
              </div>
              <div className="flex gap-1">
                <select
                  value={pathTo.type}
                  onChange={(e) => setPathTo({ ...pathTo, type: e.target.value })}
                  className="w-24 px-1 py-1 bg-slate-700 border border-slate-600 rounded text-xs text-white"
                >
                  {ALL_NODE_TYPES.map((t) => (
                    <option key={t} value={LABEL_TO_API_TYPE[t] || t.toLowerCase()}>{t}</option>
                  ))}
                </select>
                <input
                  type="text" value={pathTo.value}
                  onChange={(e) => setPathTo({ ...pathTo, value: e.target.value })}
                  placeholder="To value"
                  className="flex-1 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-xs text-white"
                />
              </div>
              <button
                onClick={handleFindPath}
                disabled={!pathFrom.value || !pathTo.value}
                className="w-full py-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white rounded text-xs"
              >
                Find Path
              </button>
              {highlightedPath.size > 0 && (
                <p className="text-xs text-cyan-400">Path highlighted ({highlightedNodes.size} nodes)</p>
              )}
            </div>
          )}
        </div>

        {/* Node Type Filter */}
        <div className="border-t border-slate-700 pt-3">
          <h4 className="text-xs text-slate-400 mb-2">Node Types</h4>
          <div className="space-y-1">
            {ALL_NODE_TYPES.map((type) => (
              <label key={type} className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={activeNodeTypes.has(type)}
                  onChange={() => toggleNodeType(type)}
                  className="rounded border-slate-600"
                />
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: NODE_COLORS[type] }} />
                {type}
              </label>
            ))}
          </div>
        </div>

        {/* Relationship Type Filter */}
        <div className="border-t border-slate-700 pt-3">
          <h4 className="text-xs text-slate-400 mb-2">Relationship Types</h4>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {ALL_REL_TYPES.map((type) => (
              <label key={type} className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={activeRelTypes.has(type)}
                  onChange={() => toggleRelType(type)}
                  className="rounded border-slate-600"
                />
                {type}
              </label>
            ))}
          </div>
        </div>

        {/* Selected Node Detail */}
        {selectedNode && (
          <div className="border-t border-slate-700 pt-3">
            <h4 className="text-sm font-medium text-white mb-2">{selectedNode._label}</h4>
            <div className="space-y-1 text-xs text-slate-300">
              {Object.entries(selectedNode)
                .filter(([k]) => !k.startsWith('_') && !['color', 'x', 'y', 'vx', 'vy', 'index', 'id', 'fx', 'fy'].includes(k))
                .map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-slate-400">{k}:</span>
                    <span className="truncate ml-2 max-w-[140px]">{String(v)}</span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>

      {/* Graph Canvas */}
      <div className="flex-1 relative">
        {nodes.length > 0 ? (
          <ForceGraph2D
            ref={graphRef}
            graphData={filteredGraphData}
            nodeLabel={(node: any) => `${node._label}: ${node.value || node.name || ''}`}
            nodeColor={(node: any) => node.color}
            nodeRelSize={6}
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const size = node._highlighted ? 8 : 5
              ctx.beginPath()
              ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
              ctx.fillStyle = node.color
              ctx.fill()

              if (node._highlighted) {
                ctx.strokeStyle = '#ffffff'
                ctx.lineWidth = 2
                ctx.stroke()
              }

              // Draw label at high zoom
              if (globalScale > 1.5) {
                const label = node.value || node.name || node.fingerprint || ''
                ctx.font = `${10 / globalScale}px Sans-Serif`
                ctx.textAlign = 'center'
                ctx.fillStyle = '#e2e8f0'
                ctx.fillText(label, node.x, node.y + size + 10 / globalScale)
              }
            }}
            linkLabel={(link: any) => link.type}
            linkColor={(link: any) => link._highlighted ? '#fbbf24' : '#475569'}
            linkWidth={(link: any) => link._highlighted ? 3 : 1}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={0.9}
            linkDirectionalParticles={(link: any) => link._highlighted ? 3 : 0}
            linkDirectionalParticleWidth={3}
            linkDirectionalParticleColor={() => '#fbbf24'}
            onNodeClick={handleNodeClick}
            onNodeRightClick={handleNodeDblClick}
            onNodeDragEnd={(node: any) => {
              node.fx = node.x
              node.fy = node.y
            }}
            backgroundColor="#0f172a"
            cooldownTicks={100}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-slate-500">
            <div className="text-center">
              <p className="text-lg mb-2">No graph data loaded</p>
              <p className="text-sm">Search for an entity or find a shortest path</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
