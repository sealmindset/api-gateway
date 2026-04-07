'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  getFacetedRowModel,
  getFacetedUniqueValues,
  flexRender,
} from '@tanstack/react-table'
import { DataTableToolbar } from './data-table-toolbar'
import { DataTablePagination } from './data-table-pagination'

// Multi-select filter: checks if row value is in the selected array
const arrIncludesFilter = (row, columnId, filterValue) => {
  if (!filterValue || filterValue.length === 0) return true
  const value = String(row.getValue(columnId) ?? '')
  return filterValue.includes(value)
}

function loadState(storageKey, key, fallback) {
  if (typeof window === 'undefined') return fallback
  try {
    const stored = localStorage.getItem(`${storageKey}:${key}`)
    return stored ? JSON.parse(stored) : fallback
  } catch {
    return fallback
  }
}

function saveState(storageKey, key, value) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(`${storageKey}:${key}`, JSON.stringify(value))
  } catch {
    // Ignore quota errors
  }
}

/**
 * Full-featured data table with TanStack React Table.
 *
 * Props:
 *   columns           - TanStack column defs (use DataTableColumnHeader for headers)
 *   data              - array of row objects
 *   searchKey         - column ID for global text search
 *   searchPlaceholder - placeholder for search input
 *   filterableColumns - array of { id, title, options: [{ label, value }] } for toolbar filter buttons
 *   storageKey        - localStorage prefix for persisting state
 *   title             - optional heading above the table
 *   emptyMessage      - shown when data is empty
 *   enableCSVExport   - show CSV export button (default true)
 *   csvFilename       - filename for CSV export
 */
export default function DataTable({
  columns,
  data,
  searchKey,
  searchPlaceholder = 'Search...',
  filterableColumns = [],
  storageKey,
  title,
  emptyMessage = 'No data available.',
  enableCSVExport = true,
  csvFilename,
}) {
  const sk = storageKey || 'data-table'

  const [sorting, setSorting] = useState(() =>
    loadState(sk, 'sorting', []),
  )
  const [columnFilters, setColumnFilters] = useState(() =>
    loadState(sk, 'columnFilters', []),
  )
  const [columnVisibility, setColumnVisibility] = useState(() =>
    loadState(sk, 'columnVisibility', {}),
  )
  const [pagination, setPagination] = useState(() =>
    loadState(sk, 'pagination', { pageIndex: 0, pageSize: 20 }),
  )

  // Persist state changes
  useEffect(() => saveState(sk, 'sorting', sorting), [sk, sorting])
  useEffect(() => saveState(sk, 'columnFilters', columnFilters), [sk, columnFilters])
  useEffect(() => saveState(sk, 'columnVisibility', columnVisibility), [sk, columnVisibility])
  useEffect(() => saveState(sk, 'pagination', pagination), [sk, pagination])

  const table = useReactTable({
    data,
    columns,
    filterFns: { arrIncludes: arrIncludesFilter },
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      pagination,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFacetedRowModel: getFacetedRowModel(),
    getFacetedUniqueValues: getFacetedUniqueValues(),
  })

  // CSV export
  const handleExportCSV = useCallback(() => {
    const visibleCols = table.getVisibleLeafColumns()
    const headers = visibleCols.map((c) =>
      typeof c.columnDef.header === 'string' ? c.columnDef.header : c.id,
    )
    const rows = table.getFilteredRowModel().rows.map((row) =>
      visibleCols.map((col) => {
        const val = String(row.getValue(col.id) ?? '')
        return `"${val.replace(/"/g, '""')}"`
      }),
    )
    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(csvFilename || title || 'export').replace(/\s+/g, '_').toLowerCase()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [table, csvFilename, title])

  return (
    <div>
      <DataTableToolbar
        table={table}
        searchKey={searchKey}
        searchPlaceholder={searchPlaceholder}
        filterableColumns={filterableColumns}
        title={title}
        onExportCSV={enableCSVExport ? handleExportCSV : undefined}
      />

      {/* Table */}
      <div className="rounded-md border border-border overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-border">
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="h-10 px-3 text-left align-middle font-medium text-muted-foreground"
                    style={header.getSize() !== 150 ? { width: header.getSize() } : undefined}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-border transition-colors hover:bg-muted/50"
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className="px-3 py-2.5 align-middle"
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td
                  colSpan={columns.length}
                  className="h-24 text-center text-muted-foreground"
                >
                  <svg className="mx-auto h-10 w-10 text-muted-foreground/40" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m6 4.125l2.25 2.25m0 0l2.25 2.25M12 11.625l2.25-2.25M12 11.625l-2.25 2.25M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
                  </svg>
                  <p className="mt-2 text-sm">{emptyMessage}</p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <DataTablePagination table={table} />
    </div>
  )
}
