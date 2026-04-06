'use client'

import { useEffect, useState } from 'react'
import { Card, Badge, Button } from '@/components/Card'
import DataTable from '@/components/DataTable'
import { DataTableColumnHeader } from '@/components/data-table-column-header'
import { formatDate } from '@/lib/utils'

const CATEGORIES = ['anomaly', 'rate_limit', 'routing', 'transform', 'documentation']

export default function PromptsPage() {
  const [prompts, setPrompts] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)

  async function loadPrompts() {
    try {
      const res = await fetch('/api/ai/prompts')
      if (res.ok) {
        const data = await res.json()
        setPrompts(Array.isArray(data) ? data : [])
      }
    } catch (e) {
      console.error('Failed to load prompts:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPrompts()
  }, [])

  async function handleSave(formData) {
    const isNew = editing === 'new'
    const url = isNew ? '/api/ai/prompts' : `/api/ai/prompts/${editing.id}`
    const method = isNew ? 'POST' : 'PUT'

    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      })
      if (res.ok) {
        setEditing(null)
        setLoading(true)
        loadPrompts()
      } else {
        const err = await res.json().catch(() => ({}))
        alert(err.detail || 'Save failed')
      }
    } catch (e) {
      console.error('Save error:', e)
    }
  }

  async function handleToggleActive(prompt) {
    try {
      await fetch(`/api/ai/prompts/${prompt.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !prompt.is_active }),
      })
      setLoading(true)
      loadPrompts()
    } catch (e) {
      console.error(e)
    }
  }

  async function handleDelete(prompt) {
    if (!confirm(`Delete prompt "${prompt.name}"? This cannot be undone.`)) return
    try {
      await fetch(`/api/ai/prompts/${prompt.id}`, { method: 'DELETE' })
      setLoading(true)
      loadPrompts()
    } catch (e) {
      console.error(e)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-200 border-t-brand-600" />
      </div>
    )
  }

  if (editing) {
    return (
      <PromptForm
        prompt={editing === 'new' ? null : editing}
        onSave={handleSave}
        onCancel={() => setEditing(null)}
      />
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
      accessorKey: 'slug',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Slug" />,
      cell: ({ row }) => <span className="font-mono text-xs">{row.getValue('slug')}</span>,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'category',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Category" />,
      cell: ({ row }) => <Badge variant={categoryBadge(row.getValue('category'))}>{row.getValue('category')}</Badge>,
      filterFn: 'arrIncludes',
    },
    {
      id: 'model',
      accessorFn: (row) => row.model || 'default',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Model" />,
      cell: ({ row }) => <span className="font-mono text-xs">{row.getValue('model')}</span>,
      filterFn: 'arrIncludes',
    },
    {
      id: 'is_active',
      accessorFn: (row) => (row.is_active ? 'Active' : 'Inactive'),
      header: ({ column }) => <DataTableColumnHeader column={column} title="Active" />,
      cell: ({ row }) => {
        const original = row.original
        return (
          <button onClick={() => handleToggleActive(original)} title="Toggle active">
            <Badge variant={row.getValue('is_active') === 'Active' ? 'success' : 'danger'}>
              {row.getValue('is_active')}
            </Badge>
          </button>
        )
      },
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'version',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Version" />,
      cell: ({ row }) => <span className="text-xs text-gray-500">v{row.getValue('version')}</span>,
      enableColumnFilter: false,
    },
    {
      accessorKey: 'updated_at',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Updated" />,
      cell: ({ row }) => <span className="text-xs text-gray-500">{formatDate(row.getValue('updated_at'))}</span>,
      enableColumnFilter: false,
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => {
        const original = row.original
        return (
          <div className="flex gap-2">
            <button onClick={() => setEditing(original)} className="text-xs font-medium text-brand-600 hover:text-brand-800">Edit</button>
            <button onClick={() => handleDelete(original)} className="text-xs font-medium text-red-600 hover:text-red-800">Delete</button>
          </div>
        )
      },
      enableSorting: false,
      enableColumnFilter: false,
      enableHiding: false,
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end">
        <Button onClick={() => setEditing('new')}>+ New Prompt</Button>
      </div>

      <Card className="p-0">
        <DataTable
          columns={columns}
          data={prompts}
          title="AI Prompts"
          storageKey="ai-prompts"
          searchKey="name"
          searchPlaceholder="Search prompts..."
          emptyMessage="No prompts found. Create your first AI prompt template to get started."
        />
      </Card>
    </div>
  )
}


function PromptForm({ prompt, onSave, onCancel }) {
  const isNew = !prompt
  const [form, setForm] = useState({
    slug: prompt?.slug || '',
    name: prompt?.name || '',
    category: prompt?.category || 'anomaly',
    system_prompt: prompt?.system_prompt || '',
    model: prompt?.model || '',
    temperature: prompt?.temperature ?? 0.3,
    max_tokens: prompt?.max_tokens ?? 4096,
    is_active: prompt?.is_active ?? true,
  })

  function set(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleSubmit(e) {
    e.preventDefault()
    const data = { ...form }
    if (!data.model) data.model = null
    if (!isNew) {
      delete data.slug
      delete data.category
    }
    onSave(data)
  }

  return (
    <Card>
      <h2 className="mb-6 text-base font-semibold text-gray-900">
        {isNew ? 'Create New Prompt' : `Edit: ${prompt.name}`}
      </h2>
      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="Name" required>
            <input
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              required
              className="input"
              placeholder="Anomaly Detection v2"
            />
          </Field>
          <Field label="Slug" required disabled={!isNew}>
            <input
              value={form.slug}
              onChange={(e) => set('slug', e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))}
              required
              disabled={!isNew}
              className="input disabled:bg-gray-100 disabled:text-gray-500"
              placeholder="anomaly-detection"
            />
          </Field>
          <Field label="Category" required>
            <select
              value={form.category}
              onChange={(e) => set('category', e.target.value)}
              disabled={!isNew}
              className="input disabled:bg-gray-100"
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </Field>
          <Field label="Model Override">
            <input
              value={form.model}
              onChange={(e) => set('model', e.target.value)}
              className="input"
              placeholder="Leave empty for default"
            />
          </Field>
          <Field label="Temperature">
            <input
              type="number"
              step="0.1"
              min="0"
              max="2"
              value={form.temperature}
              onChange={(e) => set('temperature', parseFloat(e.target.value))}
              className="input"
            />
          </Field>
          <Field label="Max Tokens">
            <input
              type="number"
              min="1"
              max="128000"
              value={form.max_tokens}
              onChange={(e) => set('max_tokens', parseInt(e.target.value, 10))}
              className="input"
            />
          </Field>
        </div>

        <Field label="System Prompt" required>
          <textarea
            value={form.system_prompt}
            onChange={(e) => set('system_prompt', e.target.value)}
            required
            rows={16}
            className="input font-mono text-xs leading-relaxed"
            placeholder="You are an expert API traffic analyst..."
          />
        </Field>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => set('is_active', e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
            />
            Active
          </label>
        </div>

        <div className="flex gap-3 border-t border-gray-200 pt-5">
          <Button type="submit">{isNew ? 'Create Prompt' : 'Save Changes'}</Button>
          <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        </div>
      </form>

      <style jsx>{`
        .input {
          width: 100%;
          border-radius: 0.5rem;
          border: 1px solid #d1d5db;
          padding: 0.5rem 0.75rem;
          font-size: 0.875rem;
        }
        .input:focus {
          outline: none;
          border-color: #3b82f6;
          box-shadow: 0 0 0 1px #3b82f6;
        }
      `}</style>
    </Card>
  )
}


function Field({ label, required, disabled, children }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      {children}
    </div>
  )
}


function categoryBadge(cat) {
  const map = {
    anomaly: 'danger',
    rate_limit: 'warning',
    routing: 'info',
    transform: 'success',
    documentation: 'default',
  }
  return map[cat] || 'default'
}
