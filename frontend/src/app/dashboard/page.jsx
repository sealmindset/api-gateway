'use client'

import { useEffect, useState } from 'react'
import { Card, StatCard, Badge } from '@/components/Card'
import DataTable from '@/components/DataTable'
import { DataTableColumnHeader } from '@/components/data-table-column-header'

export default function DashboardPage() {
  const [health, setHealth] = useState(null)
  const [services, setServices] = useState([])
  const [routes, setRoutes] = useState([])
  const [plugins, setPlugins] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [h, s, r, p] = await Promise.allSettled([
          fetch('/api/health').then((r) => r.json()),
          fetch('/api/kong/services').then((r) => r.json()),
          fetch('/api/kong/routes').then((r) => r.json()),
          fetch('/api/kong/plugins').then((r) => r.json()),
        ])
        if (h.status === 'fulfilled') setHealth(h.value)
        if (s.status === 'fulfilled') setServices(s.value.data || [])
        if (r.status === 'fulfilled') setRoutes(r.value.data || [])
        if (p.status === 'fulfilled') setPlugins(p.value.data || [])
      } catch (e) {
        console.error('Dashboard load error:', e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary/20 border-t-primary" />
      </div>
    )
  }

  const serviceCols = [
    {
      accessorKey: 'name',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />,
      cell: ({ row }) => <span className="font-medium text-foreground">{row.getValue('name')}</span>,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'host',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Host" />,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'port',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Port" />,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'protocol',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Protocol" />,
      cell: ({ row }) => <Badge variant="info">{row.getValue('protocol')}</Badge>,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'tags',
      header: 'Tags',
      cell: ({ row }) => (
        <div className="flex flex-wrap gap-1">
          {(row.getValue('tags') || []).map((t) => <Badge key={t}>{t}</Badge>)}
        </div>
      ),
      enableSorting: false,
      enableColumnFilter: false,
    },
  ]

  const routeCols = [
    {
      accessorKey: 'name',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />,
      cell: ({ row }) => <span className="font-medium text-foreground">{row.getValue('name')}</span>,
      filterFn: 'arrIncludes',
    },
    {
      id: 'paths',
      accessorFn: (row) => (row.paths || []).join(', '),
      header: ({ column }) => <DataTableColumnHeader column={column} title="Paths" />,
      cell: ({ row }) => <span className="font-mono text-xs">{row.getValue('paths')}</span>,
      filterFn: 'arrIncludes',
    },
    {
      id: 'methods',
      accessorFn: (row) => (row.methods ? row.methods.join(', ') : 'ALL'),
      header: ({ column }) => <DataTableColumnHeader column={column} title="Methods" />,
      filterFn: 'arrIncludes',
    },
    {
      id: 'protocols',
      accessorFn: (row) => (row.protocols || []).join(', '),
      header: ({ column }) => <DataTableColumnHeader column={column} title="Protocols" />,
      cell: ({ row }) => (
        <div className="flex gap-1">
          {row.getValue('protocols').split(', ').filter(Boolean).map((p) => (
            <Badge key={p} variant="info">{p}</Badge>
          ))}
        </div>
      ),
      filterFn: 'arrIncludes',
    },
    {
      id: 'strip_path',
      accessorFn: (row) => (row.strip_path ? 'Yes' : 'No'),
      header: ({ column }) => <DataTableColumnHeader column={column} title="Strip Path" />,
      cell: ({ row }) => (
        <Badge variant={row.getValue('strip_path') === 'Yes' ? 'success' : 'default'}>
          {row.getValue('strip_path')}
        </Badge>
      ),
      filterFn: 'arrIncludes',
    },
  ]

  const pluginCols = [
    {
      accessorKey: 'name',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Plugin" />,
      cell: ({ row }) => <span className="font-medium text-foreground">{row.getValue('name')}</span>,
      filterFn: 'arrIncludes',
    },
    {
      id: 'scope',
      accessorFn: (row) => (row.service?.id ? 'Service' : row.route?.id ? 'Route' : 'Global'),
      header: ({ column }) => <DataTableColumnHeader column={column} title="Scope" />,
      filterFn: 'arrIncludes',
    },
    {
      id: 'enabled',
      accessorFn: (row) => (row.enabled ? 'Enabled' : 'Disabled'),
      header: ({ column }) => <DataTableColumnHeader column={column} title="Enabled" />,
      cell: ({ row }) => (
        <Badge variant={row.getValue('enabled') === 'Enabled' ? 'success' : 'danger'}>
          {row.getValue('enabled')}
        </Badge>
      ),
      filterFn: 'arrIncludes',
    },
    {
      id: 'protocols',
      accessorFn: (row) => (row.protocols || []).join(', '),
      header: 'Protocols',
      cell: ({ row }) => (
        <div className="flex gap-1">
          {row.getValue('protocols').split(', ').filter(Boolean).map((p) => (
            <Badge key={p}>{p}</Badge>
          ))}
        </div>
      ),
      enableSorting: false,
      enableColumnFilter: false,
    },
  ]

  return (
    <div className="space-y-8">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Services" value={services.length} sub="Upstream backends" icon={ServiceIcon} />
        <StatCard label="Routes" value={routes.length} sub="Active routes" icon={RouteIcon} />
        <StatCard label="Plugins" value={plugins.length} sub="Active plugins" icon={PluginIcon} />
        <StatCard label="Health" value={health?.status === 'ok' ? 'Healthy' : 'Unknown'} sub="Admin panel status" icon={HeartIcon} />
      </div>

      <Card className="p-0">
        <DataTable columns={serviceCols} data={services} title="Gateway Services" storageKey="dash-services" emptyMessage="No services configured." />
      </Card>

      <Card className="p-0">
        <DataTable columns={routeCols} data={routes} title="Gateway Routes" storageKey="dash-routes" emptyMessage="No routes configured." />
      </Card>

      <Card className="p-0">
        <DataTable columns={pluginCols} data={plugins} title="Active Plugins" storageKey="dash-plugins" emptyMessage="No plugins enabled." />
      </Card>
    </div>
  )
}

function ServiceIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 0 1-3-3m3 3a3 3 0 1 0 0 6h13.5a3 3 0 1 0 0-6m-16.5-3a3 3 0 0 1 3-3h13.5a3 3 0 0 1 3 3m-19.5 0a4.5 4.5 0 0 1 .9-2.7L5.737 5.1a3.375 3.375 0 0 1 2.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 0 1 .9 2.7m0 0a3 3 0 0 1-3 3m0 3h.008v.008h-.008v-.008Zm0-6h.008v.008h-.008v-.008Zm-3 6h.008v.008h-.008v-.008Zm0-6h.008v.008h-.008v-.008Z" />
    </svg>
  )
}

function RouteIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21 3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
    </svg>
  )
}

function PluginIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.25 6.087c0-.355.186-.676.401-.959.221-.29.349-.634.349-1.003 0-1.036-1.007-1.875-2.25-1.875s-2.25.84-2.25 1.875c0 .369.128.713.349 1.003.215.283.401.604.401.959v0a.64.64 0 0 1-.657.643 48.39 48.39 0 0 1-4.163-.3c.186 1.613.293 3.25.315 4.907a.656.656 0 0 1-.658.663v0c-.355 0-.676-.186-.959-.401a1.647 1.647 0 0 0-1.003-.349c-1.036 0-1.875 1.007-1.875 2.25s.84 2.25 1.875 2.25c.369 0 .713-.128 1.003-.349.283-.215.604-.401.959-.401v0c.31 0 .555.26.532.57a48.039 48.039 0 0 1-.642 5.056c1.518.19 3.058.309 4.616.354a.64.64 0 0 0 .657-.643v0c0-.355-.186-.676-.401-.959a1.647 1.647 0 0 1-.349-1.003c0-1.035 1.008-1.875 2.25-1.875 1.243 0 2.25.84 2.25 1.875 0 .369-.128.713-.349 1.003-.215.283-.4.604-.4.959v0c0 .333.277.599.61.58a48.1 48.1 0 0 0 5.427-.63 48.05 48.05 0 0 0 .582-4.717.532.532 0 0 0-.533-.57v0c-.355 0-.676.186-.959.401-.29.221-.634.349-1.003.349-1.035 0-1.875-1.007-1.875-2.25s.84-2.25 1.875-2.25c.37 0 .713.128 1.003.349.283.215.604.401.96.401v0a.656.656 0 0 0 .658-.663 48.422 48.422 0 0 0-.37-5.36c-1.886.342-3.81.574-5.766.689a.578.578 0 0 1-.61-.58v0Z" />
    </svg>
  )
}

function HeartIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12Z" />
    </svg>
  )
}
