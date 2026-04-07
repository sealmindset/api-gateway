'use client'

import { useEffect, useState } from 'react'
import { Card, Badge } from '@/components/Card'
import DataTable from '@/components/DataTable'
import { DataTableColumnHeader } from '@/components/data-table-column-header'

export default function ApiKeysPage() {
  const [keys, setKeys] = useState([])
  const [consumers, setConsumers] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [keysRes, consumersRes] = await Promise.allSettled([
          fetch('/api/kong/key-auths').then((r) => r.json()),
          fetch('/api/kong/consumers').then((r) => r.json()),
        ])
        if (keysRes.status === 'fulfilled') setKeys(keysRes.value.data || [])
        if (consumersRes.status === 'fulfilled') setConsumers(consumersRes.value.data || [])
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  function consumerName(consumerId) {
    const c = consumers.find((c) => c.id === consumerId)
    return c?.username || c?.custom_id || consumerId?.slice(0, 8) || '—'
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary/20 border-t-primary" />
      </div>
    )
  }

  const consumerCols = [
    {
      accessorKey: 'username',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Username" />,
      cell: ({ row }) => <span className="font-medium text-foreground">{row.getValue('username')}</span>,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'custom_id',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Custom ID" />,
      cell: ({ row }) => <span className="font-mono text-xs">{row.getValue('custom_id') || '—'}</span>,
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
    {
      id: 'created_at',
      accessorFn: (row) => (row.created_at ? new Date(row.created_at * 1000).toLocaleDateString() : '—'),
      header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
      enableColumnFilter: false,
    },
  ]

  const keyCols = [
    {
      id: 'key_prefix',
      accessorFn: (row) => row.key?.slice(0, 12) || '',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Key (prefix)" />,
      cell: ({ row }) => <span className="font-mono text-xs text-foreground">{row.getValue('key_prefix')}...</span>,
      enableColumnFilter: false,
    },
    {
      id: 'consumer',
      accessorFn: (row) => consumerName(row.consumer?.id),
      header: ({ column }) => <DataTableColumnHeader column={column} title="Consumer" />,
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
    {
      id: 'created_at',
      accessorFn: (row) => (row.created_at ? new Date(row.created_at * 1000).toLocaleDateString() : '—'),
      header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
      enableColumnFilter: false,
    },
  ]

  return (
    <div className="space-y-6">
      <Card className="p-0">
        <DataTable
          columns={consumerCols}
          data={consumers}
          title="Kong Consumers"
          storageKey="consumers"
          searchKey="username"
          searchPlaceholder="Search consumers..."
          emptyMessage="No consumers. Consumers are created when API keys are provisioned."
        />
      </Card>

      <Card className="p-0">
        <DataTable
          columns={keyCols}
          data={keys}
          title="API Keys (Key-Auth)"
          storageKey="api-keys"
          emptyMessage="No API keys. API keys will appear here once provisioned through Kong."
        />
      </Card>
    </div>
  )
}
