'use client'

import { useEffect, useState } from 'react'
import { Card, Badge } from '@/components/Card'
import DataTable from '@/components/DataTable'
import { DataTableColumnHeader } from '@/components/data-table-column-header'

export default function GatewayPage() {
  const [services, setServices] = useState([])
  const [routes, setRoutes] = useState([])
  const [plugins, setPlugins] = useState([])
  const [upstreams, setUpstreams] = useState([])
  const [info, setInfo] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('services')

  useEffect(() => {
    async function load() {
      try {
        const [svc, rt, pl, up, inf] = await Promise.allSettled([
          fetch('/api/kong/services').then((r) => r.json()),
          fetch('/api/kong/routes').then((r) => r.json()),
          fetch('/api/kong/plugins').then((r) => r.json()),
          fetch('/api/kong/upstreams').then((r) => r.json()),
          fetch('/api/kong/').then((r) => r.json()),
        ])
        if (svc.status === 'fulfilled') setServices(svc.value.data || [])
        if (rt.status === 'fulfilled') setRoutes(rt.value.data || [])
        if (pl.status === 'fulfilled') setPlugins(pl.value.data || [])
        if (up.status === 'fulfilled') setUpstreams(up.value.data || [])
        if (inf.status === 'fulfilled') setInfo(inf.value)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-200 border-t-brand-600" />
      </div>
    )
  }

  const tabs = [
    { id: 'services', label: `Services (${services.length})` },
    { id: 'routes', label: `Routes (${routes.length})` },
    { id: 'plugins', label: `Plugins (${plugins.length})` },
    { id: 'info', label: 'Node Info' },
  ]

  const serviceCols = [
    {
      accessorKey: 'name',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />,
      cell: ({ row }) => <span className="font-medium text-gray-900">{row.getValue('name')}</span>,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'host',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Host" />,
      cell: ({ row }) => <span className="font-mono text-xs">{row.getValue('host')}</span>,
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
      id: 'timeouts',
      accessorFn: (row) => `C:${row.connect_timeout / 1000}s R:${row.read_timeout / 1000}s W:${row.write_timeout / 1000}s`,
      header: 'Timeouts',
      cell: ({ row }) => <span className="text-xs text-gray-500">{row.getValue('timeouts')}</span>,
      enableSorting: false,
      enableColumnFilter: false,
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
      cell: ({ row }) => <span className="font-medium text-gray-900">{row.getValue('name')}</span>,
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
    {
      id: 'service_name',
      accessorFn: (row) => {
        const svc = services.find((s) => s.id === row.service?.id)
        return svc?.name || row.service?.id?.slice(0, 8) || '—'
      },
      header: ({ column }) => <DataTableColumnHeader column={column} title="Service" />,
      cell: ({ row }) => <span className="text-xs">{row.getValue('service_name')}</span>,
      filterFn: 'arrIncludes',
    },
  ]

  const pluginCols = [
    {
      accessorKey: 'name',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Plugin" />,
      cell: ({ row }) => <span className="font-medium text-gray-900">{row.getValue('name')}</span>,
      filterFn: 'arrIncludes',
    },
    {
      id: 'scope',
      accessorFn: (row) => {
        if (row.service?.id) {
          const svc = services.find((s) => s.id === row.service.id)
          return `Service: ${svc?.name || row.service.id.slice(0, 8)}`
        }
        return row.route?.id ? 'Route' : 'Global'
      },
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
    <div className="space-y-6">
      {/* Kong version banner */}
      {info && (
        <Card className="flex items-center gap-4 bg-gray-50">
          <div className="rounded-lg bg-white p-2 shadow-sm">
            <svg className="h-8 w-8 text-brand-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 0 1-3-3m3 3a3 3 0 1 0 0 6h13.5a3 3 0 1 0 0-6m-16.5-3a3 3 0 0 1 3-3h13.5a3 3 0 0 1 3 3m-19.5 0a4.5 4.5 0 0 1 .9-2.7L5.737 5.1a3.375 3.375 0 0 1 2.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 0 1 .9 2.7m0 0a3 3 0 0 1-3 3m0 3h.008v.008h-.008v-.008Zm0-6h.008v.008h-.008v-.008Zm-3 6h.008v.008h-.008v-.008Zm0-6h.008v.008h-.008v-.008Z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900">Kong Gateway {info.version}</p>
            <p className="text-xs text-gray-500">
              Node: {info.node_id?.slice(0, 12)} &middot; DB: {info.configuration?.database}
              &middot; Plugins: {info.plugins?.available_on_server ? Object.keys(info.plugins.available_on_server).length : '?'} available
            </p>
          </div>
        </Card>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`border-b-2 pb-3 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'border-brand-600 text-brand-600'
                  : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {activeTab === 'services' && (
        <Card className="p-0">
          <DataTable columns={serviceCols} data={services} title="Services" storageKey="gw-services" emptyMessage="No services configured." />
        </Card>
      )}

      {activeTab === 'routes' && (
        <Card className="p-0">
          <DataTable columns={routeCols} data={routes} title="Routes" storageKey="gw-routes" emptyMessage="No routes configured." />
        </Card>
      )}

      {activeTab === 'plugins' && (
        <Card className="p-0">
          <DataTable columns={pluginCols} data={plugins} title="Plugins" storageKey="gw-plugins" emptyMessage="No plugins enabled." />
        </Card>
      )}

      {activeTab === 'info' && info && (
        <Card>
          <h2 className="mb-4 text-base font-semibold text-gray-900">Kong Node Information</h2>
          <div className="space-y-3">
            <InfoRow label="Version" value={info.version} />
            <InfoRow label="Node ID" value={info.node_id} />
            <InfoRow label="Hostname" value={info.hostname} />
            <InfoRow label="Database" value={info.configuration?.database} />
            <InfoRow label="Lua Version" value={info.lua_version} />
            <InfoRow label="Admin Listen" value={info.configuration?.admin_listen?.join(', ')} />
            <InfoRow label="Proxy Listen" value={info.configuration?.proxy_listen?.join(', ')} />
          </div>
        </Card>
      )}
    </div>
  )
}

function InfoRow({ label, value }) {
  return (
    <div className="flex items-start justify-between border-b border-gray-100 pb-3 last:border-0 last:pb-0">
      <span className="text-sm font-medium text-gray-600">{label}</span>
      <code className="max-w-md truncate rounded bg-gray-100 px-2 py-1 text-xs text-gray-800">{value || '—'}</code>
    </div>
  )
}
