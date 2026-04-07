'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { Card, Badge, Button, StatCard } from '@/components/Card'
import { formatDate } from '@/lib/utils'

const STATUS_LABELS = {
  draft: 'Draft',
  pending_review: 'Pending Review',
  approved: 'Approved',
  rejected: 'Rejected',
  active: 'Active',
  deprecated: 'Deprecated',
  retired: 'Retired',
}

const STATUS_COLORS = {
  draft: 'bg-muted text-foreground',
  pending_review: 'bg-warning/15 text-warning-foreground',
  approved: 'bg-primary/15 text-primary',
  rejected: 'bg-destructive/15 text-destructive',
  active: 'bg-success/15 text-success',
  deprecated: 'bg-warning/15 text-warning-foreground',
  retired: 'bg-muted text-muted-foreground',
}

export default function ApiDetailPage() {
  const params = useParams()
  const [api, setApi] = useState(null)
  const [usage, setUsage] = useState(null)
  const [team, setTeam] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!params.id) return

    Promise.allSettled([
      fetch(`/api/api-registry/${params.id}`).then((r) => r.json()),
      fetch(`/api/api-registry/${params.id}/usage`).then((r) => r.json()),
    ]).then(([apiResult, usageResult]) => {
      if (apiResult.status === 'fulfilled') {
        setApi(apiResult.value)
        // Fetch team info
        fetch(`/api/teams/${apiResult.value.team_id}`)
          .then((r) => r.json())
          .then(setTeam)
          .catch(() => {})
      }
      if (usageResult.status === 'fulfilled') setUsage(usageResult.value)
      setLoading(false)
    })
  }, [params.id])

  async function handleAction(action) {
    const endpoints = {
      submit: `/api/api-registry/${params.id}/submit`,
      approve: `/api/api-registry/${params.id}/review`,
      reject: `/api/api-registry/${params.id}/review`,
      activate: `/api/api-registry/${params.id}/activate`,
      deprecate: `/api/api-registry/${params.id}/status`,
      retire: `/api/api-registry/${params.id}/status`,
    }
    const bodies = {
      submit: undefined,
      approve: { action: 'approve' },
      reject: { action: 'reject', notes: prompt('Rejection reason:') },
      activate: undefined,
      deprecate: { status: 'deprecated' },
      retire: { status: 'retired' },
    }
    try {
      const res = await fetch(endpoints[action], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: bodies[action] ? JSON.stringify(bodies[action]) : undefined,
      })
      if (res.ok) {
        const updated = await res.json()
        setApi(updated)
        // Refresh usage after activation
        if (action === 'activate') {
          fetch(`/api/api-registry/${params.id}/usage`)
            .then((r) => r.json())
            .then(setUsage)
            .catch(() => {})
        }
      }
    } catch (err) {
      console.error(`${action} failed:`, err)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary/20 border-t-primary" />
      </div>
    )
  }

  if (!api) {
    return (
      <div className="py-16 text-center">
        <h2 className="text-lg font-semibold text-foreground">API Not Found</h2>
        <p className="text-sm text-muted-foreground mt-1">The requested API registration does not exist.</p>
        <a href="/api-registry" className="mt-4 inline-block text-sm text-primary hover:underline">Back to Registry</a>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="text-sm text-muted-foreground">
        <a href="/api-registry" className="text-primary hover:underline">API Registry</a>
        <span className="mx-2">/</span>
        <span className="text-foreground">{api.name}</span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-foreground">{api.name}</h1>
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[api.status]}`}>
              {STATUS_LABELS[api.status]}
            </span>
            <Badge variant="default">{api.api_type.toUpperCase()}</Badge>
            <Badge variant="info">{api.version}</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{api.description || 'No description provided'}</p>
          {team && <p className="mt-1 text-xs text-muted-foreground">Team: {team.name}</p>}
        </div>
        <div className="flex gap-2">
          {api.status === 'draft' && (
            <Button size="sm" onClick={() => handleAction('submit')}>Submit for Review</Button>
          )}
          {api.status === 'pending_review' && (
            <>
              <Button size="sm" onClick={() => handleAction('approve')}>Approve</Button>
              <Button size="sm" variant="danger" onClick={() => handleAction('reject')}>Reject</Button>
            </>
          )}
          {api.status === 'approved' && (
            <Button size="sm" onClick={() => handleAction('activate')}>Activate in Kong</Button>
          )}
          {api.status === 'active' && (
            <Button size="sm" variant="secondary" onClick={() => handleAction('deprecate')}>Deprecate</Button>
          )}
          {api.status === 'deprecated' && (
            <Button size="sm" variant="danger" onClick={() => handleAction('retire')}>Retire</Button>
          )}
        </div>
      </div>

      {/* Review Info */}
      {api.reviewed_at && (
        <Card>
          <h3 className="text-sm font-semibold text-foreground mb-2">Review Information</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Reviewed At:</span>
              <span className="ml-2 text-foreground">{formatDate(api.reviewed_at)}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Status:</span>
              <span className={`ml-2 font-medium ${api.status === 'rejected' ? 'text-destructive' : 'text-success'}`}>
                {api.status === 'rejected' ? 'Rejected' : 'Approved'}
              </span>
            </div>
            {api.review_notes && (
              <div className="col-span-2">
                <span className="text-muted-foreground">Notes:</span>
                <p className="mt-1 rounded bg-muted p-3 text-sm text-foreground">{api.review_notes}</p>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Configuration Details */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <h3 className="text-sm font-semibold text-foreground mb-4">Upstream Configuration</h3>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Upstream URL</dt>
              <dd className="font-mono text-foreground">{api.upstream_url}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Protocol</dt>
              <dd className="text-foreground">{api.upstream_protocol}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Health Check</dt>
              <dd className="font-mono text-foreground">{api.health_check_path || '—'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Auth Type</dt>
              <dd><Badge variant="info">{api.auth_type}</Badge></dd>
            </div>
            {api.documentation_url && (
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Documentation</dt>
                <dd>
                  <a href={api.documentation_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                    View Docs
                  </a>
                </dd>
              </div>
            )}
          </dl>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-foreground mb-4">Gateway Configuration</h3>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Gateway Path</dt>
              <dd className="font-mono text-foreground">{api.gateway_path || `(auto: /api/${api.slug})`}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Kong Service ID</dt>
              <dd className="font-mono text-xs text-foreground">{api.kong_service_id || '—'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Kong Route ID</dt>
              <dd className="font-mono text-xs text-foreground">{api.kong_route_id || '—'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Rate Limit / Second</dt>
              <dd className="text-foreground">{api.rate_limit_second}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Rate Limit / Minute</dt>
              <dd className="text-foreground">{api.rate_limit_minute}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Rate Limit / Hour</dt>
              <dd className="text-foreground">{api.rate_limit_hour}</dd>
            </div>
          </dl>
        </Card>
      </div>

      {/* Usage Metrics (from Kong) */}
      {usage && usage.metrics !== null && api.status === 'active' && (
        <>
          <h2 className="text-lg font-semibold text-foreground">Usage & Metrics</h2>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
            <StatCard
              label="Service Status"
              value={usage.service?.enabled ? 'Enabled' : 'Disabled'}
            />
            <StatCard
              label="Gateway Path"
              value={usage.gateway_path || '—'}
            />
            <StatCard
              label="Protocols"
              value={usage.route?.protocols?.join(', ') || '—'}
            />
            <StatCard
              label="Plugins Active"
              value={usage.plugins?.filter((p) => p.enabled).length || 0}
            />
          </div>

          {/* Plugins */}
          {usage.plugins && usage.plugins.length > 0 && (
            <Card>
              <h3 className="text-sm font-semibold text-foreground mb-4">Active Plugins</h3>
              <div className="space-y-3">
                {usage.plugins.map((plugin, idx) => (
                  <div key={idx} className="flex items-center justify-between rounded-lg border border-border p-3">
                    <div className="flex items-center gap-3">
                      <Badge variant={plugin.enabled ? 'success' : 'default'}>
                        {plugin.enabled ? 'ON' : 'OFF'}
                      </Badge>
                      <span className="text-sm font-medium text-foreground">{plugin.name}</span>
                    </div>
                    <code className="max-w-sm truncate text-xs text-muted-foreground">
                      {JSON.stringify(plugin.config).slice(0, 80)}...
                    </code>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </>
      )}

      {/* Timeline */}
      <Card>
        <h3 className="text-sm font-semibold text-foreground mb-4">Timeline</h3>
        <div className="space-y-4">
          <TimelineItem label="Created" date={api.created_at} active />
          {api.submitted_at && <TimelineItem label="Submitted for Review" date={api.submitted_at} active />}
          {api.reviewed_at && (
            <TimelineItem
              label={api.status === 'rejected' ? 'Rejected' : 'Approved'}
              date={api.reviewed_at}
              active
              variant={api.status === 'rejected' ? 'danger' : 'success'}
            />
          )}
          {api.activated_at && <TimelineItem label="Activated in Kong" date={api.activated_at} active variant="success" />}
          {api.status === 'deprecated' && <TimelineItem label="Deprecated" date={api.updated_at} active variant="warning" />}
          {api.status === 'retired' && <TimelineItem label="Retired" date={api.updated_at} active variant="danger" />}
        </div>
      </Card>
    </div>
  )
}

function TimelineItem({ label, date, active, variant = 'default' }) {
  const dotColors = {
    default: 'bg-primary',
    success: 'bg-success',
    warning: 'bg-warning',
    danger: 'bg-destructive',
  }

  return (
    <div className="flex items-center gap-3">
      <div className={`h-2.5 w-2.5 rounded-full ${active ? dotColors[variant] : 'bg-muted-foreground'}`} />
      <span className="text-sm font-medium text-foreground">{label}</span>
      <span className="text-xs text-muted-foreground">{formatDate(date)}</span>
    </div>
  )
}
