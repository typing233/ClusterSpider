import { create } from 'zustand'

export interface GraphNode {
  _id: string
  _label: string
  value?: string
  name?: string
  fingerprint?: string
  breach_name?: string
  [key: string]: unknown
}

export interface GraphEdge {
  source: string
  target: string
  type: string
  properties: Record<string, unknown>
}

interface GraphState {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedNode: GraphNode | null
  filters: {
    entityTypes: string[]
    relTypes: string[]
    depth: number
  }
  setGraphData: (nodes: GraphNode[], edges: GraphEdge[]) => void
  selectNode: (node: GraphNode | null) => void
  setFilters: (filters: Partial<GraphState['filters']>) => void
  clearGraph: () => void
}

export const useGraphStore = create<GraphState>((set) => ({
  nodes: [],
  edges: [],
  selectedNode: null,
  filters: {
    entityTypes: [],
    relTypes: [],
    depth: 2,
  },
  setGraphData: (nodes, edges) => set({ nodes, edges }),
  selectNode: (node) => set({ selectedNode: node }),
  setFilters: (filters) =>
    set((state) => ({ filters: { ...state.filters, ...filters } })),
  clearGraph: () => set({ nodes: [], edges: [], selectedNode: null }),
}))
