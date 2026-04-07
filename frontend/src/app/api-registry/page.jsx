'use client'

import { useEffect, useState } from 'react'
import { Card, Badge, Button, StatCard } from '@/components/Card'
import DataTable from '@/components/DataTable'
import { DataTableColumnHeader } from '@/components/data-table-column-header'
import { formatDate, statusColor } from '@/lib/utils'

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

export default function ApiRegistryPage() {
  const [apis, setApis] = useState([])
  const [teams, setTeams] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    Promise.allSettled([
      fetch('/api/api-registry').then((r) => r.json()),
      fetch('/api/teams?my_teams=false').then((r) => r.json()),
    ]).then(([apisResult, teamsResult]) => {
      if (apisResult.status === 'fulfilled') {
        const data = apisResult.value
        setApis(Array.isArray(data) ? data : data.items || [])
      }
      if (teamsResult.status === 'fulfilled') {
        const data = teamsResult.value
        setTeams(Array.isArray(data) ? data : data.items || [])
      }
      setLoading(false)
    })
  }, [])

  function autoSlug(name) {
    return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  }

  async function handleCreate(e) {
    e.preventDefault()
    const form = new FormData(e.target)
    const body = {
      team_id: form.get('team_id'),
      name: form.get('name'),
      slug: form.get('slug'),
      description: form.get('description'),
      version: form.get('version') || 'v1',
      api_type: form.get('api_type'),
      upstream_url: form.get('upstream_url'),
      upstream_protocol: form.get('upstream_protocol'),
      gateway_path: form.get('gateway_path') || undefined,
      health_check_path: form.get('health_check_path') || '/health',
      documentation_url: form.get('documentation_url') || undefined,
      auth_type: form.get('auth_type'),
      rate_limit_second: parseInt(form.get('rate_limit_second')) || 5,
      rate_limit_minute: parseInt(form.get('rate_limit_minute')) || 100,
      rate_limit_hour: parseInt(form.get('rate_limit_hour')) || 3000,
      requires_approval: true,
    }
    try {
      const res = await fetch('/api/api-registry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        const created = await res.json()
        setApis((prev) => [created, ...prev])
        setShowForm(false)
        e.target.reset()
      }
    } catch (err) {
      console.error('Create API registration error:', err)
    }
  }

  async function handleAction(apiId, action) {
    const endpoints = {
      submit: `/api/api-registry/${apiId}/submit`,
      approve: `/api/api-registry/${apiId}/review`,
      reject: `/api/api-registry/${apiId}/review`,
      activate: `/api/api-registry/${apiId}/activate`,
      deprecate: `/api/api-registry/${apiId}/status`,
      retire: `/api/api-registry/${apiId}/status`,
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
        setApis((prev) => prev.map((a) => (a.id === apiId ? updated : a)))
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

  const filteredApis = filter === 'all' ? apis : apis.filter((a) => a.status === filter)

  // Stats
  const stats = {
    total: apis.length,
    active: apis.filter((a) => a.status === 'active').length,
    pending: apis.filter((a) => a.status === 'pending_review').length,
    draft: apis.filter((a) => a.status === 'draft').length,
  }

  const teamMap = Object.fromEntries(teams.map((t) => [t.id, t.name]))

  const columns = [
    {
      accessorKey: 'name',
      header: ({ column }) => <DataTableColumnHeader column={column} title="API Name" />,
      cell: ({ row }) => (
        <div>
          <a href={`/api-registry/${row.original.id}`} className="font-medium text-primary hover:text-primary/80 hover:underline">
            {row.getValue('name')}
          </a>
          <div className="text-xs text-muted-foreground">{row.original.slug} &middot; {row.original.version}</div>
        </div>
      ),
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'team_id',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Team" />,
      cell: ({ row }) => teamMap[row.getValue('team_id')] || row.getValue('team_id'),
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'api_type',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Type" />,
      cell: ({ row }) => (
        <Badge variant="default">{row.getValue('api_type').toUpperCase()}</Badge>
      ),
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'status',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: ({ row }) => {
        const s = row.getValue('status')
        return (
          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[s] || 'bg-muted text-foreground'}`}>
            {STATUS_LABELS[s] || s}
          </span>
        )
      },
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'gateway_path',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Gateway Path" />,
      cell: ({ row }) => {
        const path = row.getValue('gateway_path')
        return path ? (
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-foreground">{path}</code>
        ) : (
          <span className="text-xs text-muted-foreground">Not assigned</span>
        )
      },
    },
    {
      accessorKey: 'auth_type',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Auth" />,
      cell: ({ row }) => <Badge variant="info">{row.getValue('auth_type')}</Badge>,
      filterFn: 'arrIncludes',
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => {
        const api = row.original
        return (
          <div className="flex gap-1">
            {api.status === 'draft' && (
              <button onClick={() => handleAction(api.id, 'submit')} className="rounded bg-primary/10 px-2 py-1 text-xs font-medium text-primary hover:bg-primary/15">
                Submit
              </button>
            )}
            {api.status === 'pending_review' && (
              <>
                <button onClick={() => handleAction(api.id, 'approve')} className="rounded bg-success/10 px-2 py-1 text-xs font-medium text-success hover:bg-success/15">
                  Approve
                </button>
                <button onClick={() => handleAction(api.id, 'reject')} className="rounded bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive hover:bg-destructive/15">
                  Reject
                </button>
              </>
            )}
            {api.status === 'approved' && (
              <button onClick={() => handleAction(api.id, 'activate')} className="rounded bg-success/10 px-2 py-1 text-xs font-medium text-success hover:bg-success/15">
                Activate
              </button>
            )}
            {api.status === 'active' && (
              <button onClick={() => handleAction(api.id, 'deprecate')} className="rounded bg-warning/10 px-2 py-1 text-xs font-medium text-warning-foreground hover:bg-warning/15">
                Deprecate
              </button>
            )}
            {api.status === 'deprecated' && (
              <button onClick={() => handleAction(api.id, 'retire')} className="rounded bg-muted px-2 py-1 text-xs font-medium text-foreground hover:bg-accent">
                Retire
              </button>
            )}
          </div>
        )
      },
      enableColumnFilter: false,
    },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">API Registry</h1>
          <p className="text-sm text-muted-foreground">Register, manage, and monitor APIs through the Kong gateway</p>
        </div>
        <Button onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ Register API'}
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <StatCard label="Total APIs" value={stats.total} />
        <StatCard label="Active" value={stats.active} />
        <StatCard label="Pending Review" value={stats.pending} />
        <StatCard label="Drafts" value={stats.draft} />
      </div>

      {/* Registration Form */}
      {showForm && (
        <Card>
          <h3 className="mb-4 text-sm font-semibold text-foreground">Register New API</h3>
          <form onSubmit={handleCreate} className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {/* Row 1: Identity */}
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">API Name</label>
              <input
                name="name"
                required
                onChange={(e) => {
                  const slugInput = e.target.form.elements.slug
                  if (slugInput && !slugInput.dataset.manual) slugInput.value = autoSlug(e.target.value)
                }}
                className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Slug</label>
              <input
                name="slug"
                required
                pattern="^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"
                onInput={(e) => { e.target.dataset.manual = 'true' }}
                className="w-full rounded-lg border border-border px-3 py-2 text-sm font-mono focus-visible:ring-ring focus:outline-none focus-visible:ring-1"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Team</label>
              <select name="team_id" required className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1">
                <option value="">Select a team...</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>

            {/* Row 2: Description and Docs */}
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-foreground">Description</label>
              <input name="description" className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Documentation URL</label>
              <input name="documentation_url" type="url" className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1" />
            </div>

            {/* Row 3: Upstream */}
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-foreground">Upstream URL</label>
              <input name="upstream_url" required placeholder="https://api.example.com/v1" className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Protocol</label>
              <select name="upstream_protocol" className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1">
                <option value="https">HTTPS</option>
                <option value="http">HTTP</option>
                <option value="grpc">gRPC</option>
                <option value="grpcs">gRPCs</option>
              </select>
            </div>

            {/* Row 4: Config */}
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Gateway Path</label>
              <input name="gateway_path" placeholder="/api/my-service" className="w-full rounded-lg border border-border px-3 py-2 text-sm font-mono focus-visible:ring-ring focus:outline-none focus-visible:ring-1" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">API Type</label>
              <select name="api_type" className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1">
                <option value="rest">REST</option>
                <option value="graphql">GraphQL</option>
                <option value="grpc">gRPC</option>
                <option value="websocket">WebSocket</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Auth Type</label>
              <select name="auth_type" className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1">
                <option value="key-auth">API Key</option>
                <option value="oauth2">OAuth 2.0</option>
                <option value="jwt">JWT</option>
                <option value="none">None</option>
              </select>
            </div>

            {/* Row 5: Version & Health */}
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Version</label>
              <input name="version" defaultValue="v1" className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Health Check Path</label>
              <input name="health_check_path" defaultValue="/health" className="w-full rounded-lg border border-border px-3 py-2 text-sm font-mono focus-visible:ring-ring focus:outline-none focus-visible:ring-1" />
            </div>
            <div></div>

            {/* Row 6: Rate Limits */}
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Rate Limit / Second</label>
              <input name="rate_limit_second" type="number" defaultValue={5} min={0} className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Rate Limit / Minute</label>
              <input name="rate_limit_minute" type="number" defaultValue={100} min={0} className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Rate Limit / Hour</label>
              <input name="rate_limit_hour" type="number" defaultValue={3000} min={0} className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1" />
            </div>

            <div className="sm:col-span-3">
              <Button type="submit">Register API</Button>
            </div>
          </form>
        </Card>
      )}

      {/* Status Filter */}
      <div className="flex gap-2">
        {['all', 'draft', 'pending_review', 'approved', 'active', 'deprecated', 'retired'].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              filter === s
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-accent'
            }`}
          >
            {s === 'all' ? 'All' : STATUS_LABELS[s]}
            {s !== 'all' && ` (${apis.filter((a) => a.status === s).length})`}
          </button>
        ))}
      </div>

      {/* Table */}
      <Card className="p-0">
        <DataTable
          columns={columns}
          data={filteredApis}
          title="Registered APIs"
          storageKey="api-registry"
          searchKey="name"
          searchPlaceholder="Search APIs..."
          emptyMessage="No APIs registered yet. Click 'Register API' to submit your first API."
        />
      </Card>
    </div>
  )
}
