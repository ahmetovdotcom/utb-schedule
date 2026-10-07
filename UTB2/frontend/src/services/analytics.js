// Usage statistics are best-effort and must never block viewing a timetable.
const API_URL = (import.meta.env.VITE_API_URL || '/api/v1').replace(/\/$/, '')
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const uuid = () => {
  if (crypto.randomUUID) return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 15) | 64
  bytes[8] = (bytes[8] & 63) | 128
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
export function track(kind, mode, targetId = null, errorCode = null) {
  try {
    if (navigator.doNotTrack === '1' || navigator.globalPrivacyControl === true) return
    let visitor = localStorage.getItem('usage_visitor')
    if (!UUID.test(visitor || '')) { visitor = uuid(); localStorage.setItem('usage_visitor', visitor) }
    let visit = localStorage.getItem('usage_visit')
    const now = Date.now()
    const last = Number(localStorage.getItem('usage_last') || 0)
    if (!UUID.test(visit || '') || now - last >= 30 * 60 * 1000 || last > now) {
      visit = uuid()
      localStorage.setItem('usage_visit', visit)
    }
    localStorage.setItem('usage_last', String(now))
    const ua = navigator.userAgent
    const device = /iPad|Tablet/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)
      ? 'tablet' : /Mobi|Android|iPhone/i.test(ua) ? 'phone' : 'desktop'
    const browser = /Edg/i.test(ua) ? 'Edge' : /Firefox|FxiOS/i.test(ua) ? 'Firefox'
      : /Chrome|CriOS/i.test(ua) ? 'Chrome' : /Safari/i.test(ua) ? 'Safari' : 'Other'
    let referrer = ''
    try {
      const host = new URL(document.referrer).hostname
      if (host !== location.hostname) referrer = host
    } catch { /* Direct visit. */ }
    const payload = { id: uuid(), visitor, visit, kind, mode, target_id: targetId,
      device, browser, referrer, error_code: errorCode }
    void fetch(`${API_URL}/analytics/events`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, credentials: 'omit',
      body: JSON.stringify(payload), keepalive: true }).catch(() => {})
  } catch { /* Storage or analytics may be unavailable; schedules still work. */ }
}
