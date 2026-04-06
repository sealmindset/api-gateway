'use client'

import { useEffect, useState } from 'react'
import { Card, Badge, Button } from '@/components/Card'
import DataTable from '@/components/DataTable'
import { DataTableColumnHeader } from '@/components/data-table-column-header'
import { formatDate, statusColor } from '@/lib/utils'

export default function SubscribersPage() {
  const [subscribers, setSubscribers] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)

  useEffect(() => {
    fetch('/api/subscribers')
      .then((r) => r.json())
      .then((data) => setSubscribers(Array.isArray(data) ? data : data.items || []))
      .catch(() => setSubscribers([]))
      .finally(() => setLoading(false))
  }, [])

  async function handleCreate(e) {
    e.preventDefault()
    const form = new FormData(e.target)
    const body = {
      name: form.get('name'),
      email: form.get('email'),
      organization: form.get('organization'),
      tier: form.get('tier'),
    }
    try {
      const res = await fetch('/api/subscribers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        const created = await res.json()
        setSubscribers((prev) => [created, ...prev])
        setShowForm(false)
        e.target.reset()
      }
    } catch (err) {
      console.error('Create subscriber error:', err)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-200 border-t-brand-600" />
      </div>
    )
  }

  const columns = [
    {
      accessorKey: 'name',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />,
      cell: ({ row }) => <span className="font-medium text-gray-900">{row.getValue('name')}</span>,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'email',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Email" />,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'organization',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Organization" />,
      cell: ({ row }) => row.getValue('organization') || '—',
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'tier',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Tier" />,
      cell: ({ row }) => {
        const tier = row.getValue('tier')
        return (
          <Badge variant={tier === 'enterprise' ? 'info' : tier === 'premium' ? 'success' : 'default'}>
            {tier}
          </Badge>
        )
      },
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'status',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: ({ row }) => {
        const status = row.getValue('status')
        return (
          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${statusColor(status)}`}>
            {status}
          </span>
        )
      },
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'created_at',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
      cell: ({ row }) => <span className="text-xs text-gray-500">{formatDate(row.getValue('created_at'))}</span>,
      enableColumnFilter: false,
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end">
        <Button onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ Add Subscriber'}
        </Button>
      </div>

      {showForm && (
        <Card>
          <h3 className="mb-4 text-sm font-semibold text-gray-900">New Subscriber</h3>
          <form onSubmit={handleCreate} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">Name</label>
              <input name="name" required className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">Email</label>
              <input name="email" type="email" required className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">Organization</label>
              <input name="organization" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">Tier</label>
              <select name="tier" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500">
                <option value="free">Free</option>
                <option value="standard">Standard</option>
                <option value="premium">Premium</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </div>
            <div className="sm:col-span-2">
              <Button type="submit">Create Subscriber</Button>
            </div>
          </form>
        </Card>
      )}

      <Card className="p-0">
        <DataTable
          columns={columns}
          data={subscribers}
          title="Subscribers"
          storageKey="subscribers"
          searchKey="name"
          searchPlaceholder="Search subscribers..."
          emptyMessage="No subscribers yet. Add your first API subscriber to get started."
        />
      </Card>
    </div>
  )
}
