import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Merge Tailwind CSS classes with clsx + tailwind-merge.
 */
export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

/**
 * Format an ISO date string to a human-readable format.
 */
export function formatDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Map a status string to a semantic variant name for themed badges.
 */
export function statusVariant(status) {
  const s = (status || '').toLowerCase().replace(/[\s-]/g, '_')
  const map = {
    active: 'success',
    healthy: 'success',
    ok: 'success',
    approved: 'primary',
    pending_review: 'warning',
    pending: 'warning',
    draft: 'secondary',
    rejected: 'destructive',
    deprecated: 'warning',
    retired: 'secondary',
    inactive: 'secondary',
    suspended: 'destructive',
    unhealthy: 'destructive',
    error: 'destructive',
    warning: 'warning',
  }
  return map[s] || 'secondary'
}

// Keep backward compat for pages that still use statusColor
export function statusColor(status) {
  const variant = statusVariant(status)
  const map = {
    success: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    primary: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
    warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    destructive: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    secondary: 'bg-secondary text-secondary-foreground',
  }
  return map[variant] || map.secondary
}
