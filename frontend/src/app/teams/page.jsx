'use client'

import { useEffect, useState } from 'react'
import { Card, Badge, Button } from '@/components/Card'
import DataTable from '@/components/DataTable'
import { DataTableColumnHeader } from '@/components/data-table-column-header'
import { formatDate } from '@/lib/utils'

export default function TeamsPage() {
  const [teams, setTeams] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [selectedTeam, setSelectedTeam] = useState(null)
  const [members, setMembers] = useState([])
  const [showMemberForm, setShowMemberForm] = useState(false)

  useEffect(() => {
    fetchTeams()
  }, [])

  async function fetchTeams() {
    try {
      const res = await fetch('/api/teams?my_teams=false')
      const data = await res.json()
      setTeams(Array.isArray(data) ? data : data.items || [])
    } catch {
      setTeams([])
    } finally {
      setLoading(false)
    }
  }

  async function handleCreate(e) {
    e.preventDefault()
    const form = new FormData(e.target)
    const body = {
      name: form.get('name'),
      slug: form.get('slug'),
      description: form.get('description'),
      contact_email: form.get('contact_email'),
    }
    try {
      const res = await fetch('/api/teams', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        const created = await res.json()
        setTeams((prev) => [created, ...prev])
        setShowForm(false)
        e.target.reset()
      }
    } catch (err) {
      console.error('Create team error:', err)
    }
  }

  async function selectTeam(team) {
    setSelectedTeam(team)
    try {
      const res = await fetch(`/api/teams/${team.id}/members`)
      const data = await res.json()
      setMembers(Array.isArray(data) ? data : [])
    } catch {
      setMembers([])
    }
  }

  async function handleAddMember(e) {
    e.preventDefault()
    const form = new FormData(e.target)
    const body = {
      user_id: form.get('user_id'),
      role: form.get('role'),
    }
    try {
      const res = await fetch(`/api/teams/${selectedTeam.id}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        const added = await res.json()
        setMembers((prev) => [...prev, added])
        setShowMemberForm(false)
        e.target.reset()
      }
    } catch (err) {
      console.error('Add member error:', err)
    }
  }

  async function removeMember(memberId) {
    if (!confirm('Remove this member from the team?')) return
    try {
      await fetch(`/api/teams/${selectedTeam.id}/members/${memberId}`, { method: 'DELETE' })
      setMembers((prev) => prev.filter((m) => m.id !== memberId))
    } catch (err) {
      console.error('Remove member error:', err)
    }
  }

  function autoSlug(name) {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary/20 border-t-primary" />
      </div>
    )
  }

  const columns = [
    {
      accessorKey: 'name',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Team Name" />,
      cell: ({ row }) => (
        <button
          onClick={() => selectTeam(row.original)}
          className="font-medium text-primary hover:text-primary/80 hover:underline"
        >
          {row.getValue('name')}
        </button>
      ),
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'slug',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Slug" />,
      cell: ({ row }) => (
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-foreground">
          {row.getValue('slug')}
        </code>
      ),
    },
    {
      accessorKey: 'contact_email',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Contact" />,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'member_count',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Members" />,
      cell: ({ row }) => (
        <Badge variant="default">{row.getValue('member_count')}</Badge>
      ),
      enableColumnFilter: false,
    },
    {
      accessorKey: 'api_count',
      header: ({ column }) => <DataTableColumnHeader column={column} title="APIs" />,
      cell: ({ row }) => (
        <Badge variant="info">{row.getValue('api_count')}</Badge>
      ),
      enableColumnFilter: false,
    },
    {
      accessorKey: 'created_at',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
      cell: ({ row }) => <span className="text-xs text-muted-foreground">{formatDate(row.getValue('created_at'))}</span>,
      enableColumnFilter: false,
    },
  ]

  const roleColor = (role) => {
    const map = { owner: 'danger', admin: 'warning', member: 'default', viewer: 'info' }
    return map[role] || 'default'
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">Teams</h1>
          <p className="text-sm text-muted-foreground">Manage teams that own and operate APIs</p>
        </div>
        <Button onClick={() => { setShowForm(!showForm); setSelectedTeam(null) }}>
          {showForm ? 'Cancel' : '+ Create Team'}
        </Button>
      </div>

      {showForm && (
        <Card>
          <h3 className="mb-4 text-sm font-semibold text-foreground">New Team</h3>
          <form onSubmit={handleCreate} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Team Name</label>
              <input
                name="name"
                required
                onChange={(e) => {
                  const slugInput = e.target.form.elements.slug
                  if (slugInput && !slugInput.dataset.manual) {
                    slugInput.value = autoSlug(e.target.value)
                  }
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
              <label className="mb-1 block text-xs font-medium text-foreground">Contact Email</label>
              <input
                name="contact_email"
                type="email"
                required
                className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Description</label>
              <input
                name="description"
                className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1"
              />
            </div>
            <div className="sm:col-span-2">
              <Button type="submit">Create Team</Button>
            </div>
          </form>
        </Card>
      )}

      {/* Team Detail Panel */}
      {selectedTeam && !showForm && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-semibold text-foreground">{selectedTeam.name}</h3>
              <p className="text-sm text-muted-foreground">{selectedTeam.description || 'No description'}</p>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setShowMemberForm(!showMemberForm)}>
                {showMemberForm ? 'Cancel' : '+ Add Member'}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setSelectedTeam(null)}>
                Close
              </Button>
            </div>
          </div>

          {showMemberForm && (
            <form onSubmit={handleAddMember} className="mb-4 flex gap-3 items-end rounded-lg bg-muted p-4">
              <div className="flex-1">
                <label className="mb-1 block text-xs font-medium text-foreground">User ID</label>
                <input
                  name="user_id"
                  required
                  placeholder="UUID of the user to add"
                  className="w-full rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-foreground">Role</label>
                <select name="role" className="rounded-lg border border-border px-3 py-2 text-sm focus-visible:ring-ring focus:outline-none focus-visible:ring-1">
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                  <option value="viewer">Viewer</option>
                  <option value="owner">Owner</option>
                </select>
              </div>
              <Button type="submit" size="sm">Add</Button>
            </form>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">User</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Email</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Role</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Joined</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {members.map((m) => (
                  <tr key={m.id}>
                    <td className="px-4 py-3 font-medium text-foreground">{m.user_name || m.user_id}</td>
                    <td className="px-4 py-3 text-muted-foreground">{m.user_email || '—'}</td>
                    <td className="px-4 py-3"><Badge variant={roleColor(m.role)}>{m.role}</Badge></td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{formatDate(m.joined_at)}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => removeMember(m.id)}
                        className="text-xs text-destructive hover:text-destructive/80"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
                {members.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-sm text-muted-foreground">No members found</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card className="p-0">
        <DataTable
          columns={columns}
          data={teams}
          title="Teams"
          storageKey="teams"
          searchKey="name"
          searchPlaceholder="Search teams..."
          emptyMessage="No teams yet. Create your first team to start registering APIs."
        />
      </Card>
    </div>
  )
}
