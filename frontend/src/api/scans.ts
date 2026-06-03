import api from './client'

export async function createScan(target: string, targetType: string, moduleNames?: string[]) {
  const res = await api.post('/scans', {
    target,
    target_type: targetType,
    module_names: moduleNames,
  })
  return res.data
}

export async function getScan(taskId: string) {
  const res = await api.get(`/scans/${taskId}`)
  return res.data
}

export async function cancelScan(taskId: string) {
  const res = await api.delete(`/scans/${taskId}`)
  return res.data
}

export async function createReport(target: string, targetType: string, format: string) {
  const res = await api.post('/reports', { target, target_type: targetType, format })
  return res.data
}

export async function getReport(taskId: string) {
  const res = await api.get(`/reports/${taskId}`)
  return res.data
}
