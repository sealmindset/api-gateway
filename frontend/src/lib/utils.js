export function cn(...classes) {
  return classes.filter(Boolean).join(' ')
}

export function formatDate(dateStr) {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function statusColor(status) {
  const map = {
    active: 'bg-green-100 text-green-800',
    healthy: 'bg-green-100 text-green-800',
    ok: 'bg-green-100 text-green-800',
    inactive: 'bg-gray-100 text-gray-800',
    suspended: 'bg-red-100 text-red-800',
    unhealthy: 'bg-red-100 text-red-800',
    warning: 'bg-yellow-100 text-yellow-800',
    pending: 'bg-yellow-100 text-yellow-800',
  }
  return map[status?.toLowerCase()] || 'bg-gray-100 text-gray-800'
}
