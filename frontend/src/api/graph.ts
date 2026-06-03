import api from './client'

export async function getNode(entityType: string, value: string) {
  const res = await api.get(`/graph/nodes/${entityType}/${value}`)
  return res.data
}

export async function getNeighbors(
  entityType: string,
  value: string,
  depth: number = 2,
  relTypes?: string[]
) {
  const params: Record<string, string | number> = {
    entity_type: entityType,
    value,
    depth,
  }
  if (relTypes?.length) {
    params.rel_types = relTypes.join(',')
  }
  const res = await api.get('/graph/neighbors', { params })
  return res.data
}

export async function getShortestPath(
  fromType: string,
  fromValue: string,
  toType: string,
  toValue: string
) {
  const res = await api.get('/graph/path', {
    params: { from_type: fromType, from_value: fromValue, to_type: toType, to_value: toValue },
  })
  return res.data
}

export async function searchNodes(query: string, limit: number = 20) {
  const res = await api.get('/graph/search', { params: { q: query, limit } })
  return res.data
}

export async function getGraphStats() {
  const res = await api.get('/graph/stats')
  return res.data
}
