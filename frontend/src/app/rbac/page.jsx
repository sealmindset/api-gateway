'use client'

import { useEffect, useState } from 'react'
import { Card, Badge, Button, StatCard } from '@/components/Card'
import DataTable from '@/components/DataTable'
import { DataTableColumnHeader } from '@/components/data-table-column-header'
import { formatDate } from '@/lib/utils'

const ROLE_COLORS = {
  super_admin: 'danger',
  admin: 'warning',
  operator: 'info',
  viewer: 'default',
}

export default function RbacPage() {
  const [tab, setTab] = useState('users')
  const [users, setUsers] = useState([])
  const [roles, setRoles] = useState([])
  const [permissions, setPermissions] = useState([])
  const [auditLogs, setAuditLogs] = useState([])
  const [loading, setLoading] = useState(true)

  // Modal state
  const [showAssignModal, setShowAssignModal] = useState(false)
  const [assignTarget, setAssignTarget] = useState(null)
  const [showRoleForm, setShowRoleForm] = useState(false)
  const [editingRole, setEditingRole] = useState(null)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    const results = await Promise.allSettled([
      fetch('/api/rbac/users').then((r) => r.json()),
      fetch('/api/rbac/roles').then((r) => r.json()),
      fetch('/api/rbac/permissions').then((r) => r.json()),
      fetch('/api/rbac/audit?page_size=50').then((r) => r.json()),
    ])

    if (results[0].status === 'fulfilled') {
      const d = results[0].value
      setUsers(Array.isArray(d) ? d : d.items || [])
    }
    if (results[1].status === 'fulfilled') {
      setRoles(Array.isArray(results[1].value) ? results[1].value : [])
    }
    if (results[2].status === 'fulfilled') {
      setPermissions(results[2].value.permissions || [])
    }
    if (results[3].status === 'fulfilled') {
      const d = results[3].value
      setAuditLogs(Array.isArray(d) ? d : d.items || [])
    }
    setLoading(false)
  }

  // ---- Role Assignment ----

  async function assignRole(userId, roleId) {
    try {
      const res = await fetch('/api/rbac/assignments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, role_id: roleId }),
      })
      if (res.ok) {
        setShowAssignModal(false)
        setAssignTarget(null)
        loadData()
      } else {
        const err = await res.json().catch(() => ({}))
        alert(err.detail || 'Failed to assign role')
      }
    } catch (err) {
      console.error('Assign role error:', err)
    }
  }

  async function revokeRole(userId, roleId) {
    if (!confirm('Revoke this role from the user?')) return
    try {
      const res = await fetch(`/api/rbac/assignments/${userId}/${roleId}`, { method: 'DELETE' })
      if (res.ok || res.status === 204) {
        loadData()
      }
    } catch (err) {
      console.error('Revoke role error:', err)
    }
  }

  // ---- Role CRUD ----

  async function handleCreateRole(e) {
    e.preventDefault()
    const form = new FormData(e.target)
    const selectedPerms = permissions.reduce((acc, p) => {
      acc[p] = form.get(`perm_${p}`) === 'on'
      return acc
    }, {})
    const body = {
      name: form.get('name'),
      description: form.get('description'),
      permissions: selectedPerms,
    }
    try {
      const url = editingRole ? `/api/rbac/roles/${editingRole.id}` : '/api/rbac/roles'
      const method = editingRole ? 'PATCH' : 'POST'
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        setShowRoleForm(false)
        setEditingRole(null)
        loadData()
      } else {
        const err = await res.json().catch(() => ({}))
        alert(err.detail || 'Failed to save role')
      }
    } catch (err) {
      console.error('Role save error:', err)
    }
  }

  async function deleteRole(roleId) {
    if (!confirm('Delete this role? All user assignments will be removed.')) return
    try {
      await fetch(`/api/rbac/roles/${roleId}`, { method: 'DELETE' })
      loadData()
    } catch (err) {
      console.error('Delete role error:', err)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary/20 border-t-primary" />
      </div>
    )
  }

  // Group permissions by resource for the role form
  const permGroups = permissions.reduce((acc, p) => {
    const [resource] = p.split(':')
    if (!acc[resource]) acc[resource] = []
    acc[resource].push(p)
    return acc
  }, {})

  // ---- Columns ----

  const userColumns = [
    {
      accessorKey: 'name',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />,
      cell: ({ row }) => <span className="font-medium text-foreground">{row.getValue('name')}</span>,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'email',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Email" />,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'role_names',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Roles" />,
      cell: ({ row }) => {
        const roleNames = row.getValue('role_names') || []
        return (
          <div className="flex flex-wrap gap-1">
            {roleNames.length > 0 ? (
              roleNames.map((r) => (
                <Badge key={r} variant={ROLE_COLORS[r] || 'default'}>{r}</Badge>
              ))
            ) : (
              <span className="text-xs text-muted-foreground">No roles</span>
            )}
          </div>
        )
      },
      filterFn: (row, columnId, filterValue) => {
        const roles = row.getValue(columnId) || []
        return filterValue.some((v) => roles.includes(v))
      },
    },
    {
      accessorKey: 'last_login',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Last Login" />,
      cell: ({ row }) => (
        <span className="text-xs text-muted-foreground">{formatDate(row.getValue('last_login'))}</span>
      ),
      enableColumnFilter: false,
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => {
        const u = row.original
        return (
          <div className="flex gap-1">
            <button
              onClick={() => { setAssignTarget(u); setShowAssignModal(true) }}
              className="rounded bg-primary/10 px-2 py-1 text-xs font-medium text-primary hover:bg-primary/15"
            >
              Manage Roles
            </button>
          </div>
        )
      },
      enableColumnFilter: false,
    },
  ]

  const auditColumns = [
    {
      accessorKey: 'created_at',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Time" />,
      cell: ({ row }) => <span className="text-xs text-muted-foreground">{formatDate(row.getValue('created_at'))}</span>,
      enableColumnFilter: false,
    },
    {
      accessorKey: 'action',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Action" />,
      cell: ({ row }) => {
        const action = row.getValue('action')
        const variant = action === 'access_denied' ? 'danger'
          : action === 'access_granted' ? 'success'
          : action.includes('delete') || action.includes('revoke') ? 'warning'
          : 'default'
        return <Badge variant={variant}>{action}</Badge>
      },
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'resource_type',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Resource" />,
      filterFn: 'arrIncludes',
    },
    {
      accessorKey: 'resource_id',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Resource ID" />,
      cell: ({ row }) => {
        const val = row.getValue('resource_id')
        return val ? (
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-foreground">{val}</code>
        ) : '—'
      },
    },
    {
      accessorKey: 'ip_address',
      header: ({ column }) => <DataTableColumnHeader column={column} title="IP" />,
      cell: ({ row }) => (
        <span className="font-mono text-xs text-muted-foreground">{row.getValue('ip_address') || '—'}</span>
      ),
      enableColumnFilter: false,
    },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-foreground">Access Control</h1>
        <p className="text-sm text-muted-foreground">Manage platform roles, user assignments, and review the audit trail</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <StatCard label="Total Users" value={users.length} />
        <StatCard label="Roles Defined" value={roles.length} />
        <StatCard label="Permissions" value={permissions.length} />
        <StatCard label="Unassigned Users" value={users.filter((u) => !u.role_names?.length).length} />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        {[
          { key: 'users', label: 'Users & Assignments' },
          { key: 'roles', label: 'Roles' },
          { key: 'audit', label: 'Audit Log' },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              tab === t.key ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-accent-foreground'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* =============== USERS TAB =============== */}
      {tab === 'users' && (
        <>
          {/* Role Assignment Modal */}
          {showAssignModal && assignTarget && (
            <Card>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    Manage Roles: {assignTarget.name}
                  </h3>
                  <p className="text-xs text-muted-foreground">{assignTarget.email}</p>
                </div>
                <Button size="sm" variant="secondary" onClick={() => { setShowAssignModal(false); setAssignTarget(null) }}>
                  Close
                </Button>
              </div>

              {/* Current roles */}
              <div className="mb-4">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Current Roles</h4>
                {assignTarget.role_names?.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {assignTarget.role_names.map((roleName) => {
                      const roleObj = roles.find((r) => r.name === roleName)
                      return (
                        <div key={roleName} className="flex items-center gap-2 rounded-lg border border-border px-3 py-1.5">
                          <Badge variant={ROLE_COLORS[roleName] || 'default'}>{roleName}</Badge>
                          <button
                            onClick={() => roleObj && revokeRole(assignTarget.id, roleObj.id)}
                            className="text-xs text-destructive hover:text-destructive/80"
                          >
                            Revoke
                          </button>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No roles assigned</p>
                )}
              </div>

              {/* Assign new role */}
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Assign Role</h4>
                <div className="flex flex-wrap gap-2">
                  {roles
                    .filter((r) => !assignTarget.role_names?.includes(r.name))
                    .map((role) => (
                      <button
                        key={role.id}
                        onClick={() => assignRole(assignTarget.id, role.id)}
                        className="flex items-center gap-2 rounded-lg border border-dashed border-border px-3 py-1.5 text-sm text-muted-foreground hover:border-primary hover:text-primary transition-colors"
                      >
                        <span>+</span>
                        <Badge variant={ROLE_COLORS[role.name] || 'default'}>{role.name}</Badge>
                      </button>
                    ))}
                  {roles.filter((r) => !assignTarget.role_names?.includes(r.name)).length === 0 && (
                    <p className="text-sm text-muted-foreground">All roles already assigned</p>
                  )}
                </div>
              </div>
            </Card>
          )}

          <Card className="p-0">
            <DataTable
              columns={userColumns}
              data={users}
              title="Users"
              storageKey="rbac-users"
              searchKey="name"
              searchPlaceholder="Search users..."
              emptyMessage="No users found. Users are auto-provisioned on first login via Entra ID."
            />
          </Card>
        </>
      )}

      {/* =============== ROLES TAB =============== */}
      {tab === 'roles' && (
        <>
          <div className="flex justify-end">
            <Button onClick={() => { setShowRoleForm(!showRoleForm); setEditingRole(null) }}>
              {showRoleForm ? 'Cancel' : '+ Create Role'}
            </Button>
          </div>

          {/* Role Form */}
          {showRoleForm && (
            <Card>
              <h3 className="mb-4 text-sm font-semibold text-foreground">
                {editingRole ? `Edit Role: ${editingRole.name}` : 'Create New Role'}
              </h3>
              <form onSubmit={handleCreateRole} className="space-y-4">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-foreground">Role Name</label>
                    <input
                      name="name"
                      required
                      defaultValue={editingRole?.name || ''}
                      disabled={!!editingRole}
                      className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus-visible:ring-ring disabled:bg-muted"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-foreground">Description</label>
                    <input
                      name="description"
                      defaultValue={editingRole?.description || ''}
                      className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus-visible:ring-ring"
                    />
                  </div>
                </div>

                {/* Permissions grid */}
                <div>
                  <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">Permissions</label>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {Object.entries(permGroups).map(([resource, perms]) => (
                      <div key={resource} className="rounded-lg border border-border p-3">
                        <h4 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">{resource}</h4>
                        <div className="space-y-1">
                          {perms.map((p) => {
                            const action = p.split(':')[1]
                            const checked = editingRole?.permissions?.[p] || false
                            return (
                              <label key={p} className="flex items-center gap-2 text-sm text-foreground">
                                <input
                                  type="checkbox"
                                  name={`perm_${p}`}
                                  defaultChecked={checked}
                                  className="rounded border-border text-primary focus-visible:ring-ring"
                                />
                                {action}
                              </label>
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <Button type="submit">{editingRole ? 'Update Role' : 'Create Role'}</Button>
              </form>
            </Card>
          )}

          {/* Roles list */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {roles.map((role) => {
              const permCount = Object.values(role.permissions || {}).filter(Boolean).length
              const userCount = users.filter((u) => u.role_names?.includes(role.name)).length
              return (
                <Card key={role.id}>
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <Badge variant={ROLE_COLORS[role.name] || 'default'}>{role.name}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{role.description}</p>
                    </div>
                    <div className="flex gap-1">
                      <button
                        onClick={() => { setEditingRole(role); setShowRoleForm(true) }}
                        className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                        title="Edit role"
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
                        </svg>
                      </button>
                      <button
                        onClick={() => deleteRole(role.id)}
                        className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        title="Delete role"
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                        </svg>
                      </button>
                    </div>
                  </div>
                  <div className="flex gap-4 text-xs text-muted-foreground">
                    <span>{permCount} permissions</span>
                    <span>{userCount} {userCount === 1 ? 'user' : 'users'}</span>
                  </div>

                  {/* Permission summary */}
                  <div className="mt-3 flex flex-wrap gap-1">
                    {Object.entries(role.permissions || {})
                      .filter(([, v]) => v)
                      .slice(0, 8)
                      .map(([p]) => (
                        <span key={p} className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          {p}
                        </span>
                      ))}
                    {Object.values(role.permissions || {}).filter(Boolean).length > 8 && (
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        +{Object.values(role.permissions).filter(Boolean).length - 8} more
                      </span>
                    )}
                  </div>
                </Card>
              )
            })}
          </div>
        </>
      )}

      {/* =============== AUDIT TAB =============== */}
      {tab === 'audit' && (
        <Card className="p-0">
          <DataTable
            columns={auditColumns}
            data={auditLogs}
            title="Audit Log"
            storageKey="rbac-audit"
            searchKey="action"
            searchPlaceholder="Search actions..."
            emptyMessage="No audit log entries yet."
          />
        </Card>
      )}
    </div>
  )
}
