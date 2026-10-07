const API_URL = (import.meta.env.VITE_API_URL || '/api/v1').replace(/\/$/, '')

async function read(path) {
  const response = await fetch(`${API_URL}${path}`, { cache: 'no-store' })
  if (!response.ok) {
    const error = new Error(`Ошибка загрузки: ${response.status}`)
    error.status = response.status
    throw error
  }
  return response.json()
}

export const scheduleApi = {
  getTeachers: () => read('/teachers'),
  getTeacherSchedule: (id, day) => read(`/teachers/${id}/schedule?day=${day}`),
  getGroups: () => read('/groups'),
  getPublication: () => read('/publication'),
  getSchedule: (groupId, day) => read(`/schedules/${groupId}?day=${day}`),
}
