'use client'

import { useState, useRef, useEffect } from 'react'
import { Search, X, Filter, ChevronDown, Eye, Download } from 'lucide-react'
import { cn } from '@/lib/utils'

export function DataTableToolbar({
  table,
  searchKey,
  searchPlaceholder = 'Search...',
  filterableColumns = [],
  title,
  onExportCSV,
}) {
  const activeFilterCount = table.getState().columnFilters.length
  const searchValue = searchKey
    ? (table.getColumn(searchKey)?.getFilterValue() ?? '')
    : ''

  const isFiltered =
    activeFilterCount > 0 || (searchKey && searchValue.length > 0)

  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-3">
      {title && (
        <h2 className="mr-2 text-base font-semibold text-gray-900">{title}</h2>
      )}

      {/* Global search on a specific column */}
      {searchKey && (
        <div className="relative min-w-[200px] max-w-sm flex-1">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            placeholder={searchPlaceholder}
            value={searchValue}
            onChange={(e) =>
              table.getColumn(searchKey)?.setFilterValue(e.target.value)
            }
            className="w-full rounded-md border border-gray-200 bg-white py-1.5 pl-8 pr-3 text-sm outline-none placeholder:text-gray-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
          />
        </div>
      )}

      {/* Faceted filter buttons */}
      {filterableColumns.map((fc) => {
        const column = table.getColumn(fc.id)
        if (!column) return null
        return (
          <FacetedFilterButton
            key={fc.id}
            column={column}
            title={fc.title}
            options={fc.options}
          />
        )
      })}

      {/* Active filter count badge */}
      {activeFilterCount > 0 && (
        <span className="inline-flex items-center rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-medium text-brand-700">
          {activeFilterCount} filter{activeFilterCount !== 1 ? 's' : ''}
        </span>
      )}

      {/* Reset all filters */}
      {isFiltered && (
        <button
          onClick={() => table.resetColumnFilters()}
          className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-2.5 py-1 text-xs text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-700"
        >
          <X className="h-3 w-3" />
          Reset
        </button>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Row count */}
      <span className="text-xs text-gray-500">
        {table.getFilteredRowModel().rows.length} row{table.getFilteredRowModel().rows.length !== 1 ? 's' : ''}
      </span>

      {/* CSV export */}
      {onExportCSV && (
        <button
          onClick={onExportCSV}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-gray-200 bg-white px-2.5 text-xs text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900"
          title="Export CSV"
        >
          <Download className="h-3.5 w-3.5" />
          CSV
        </button>
      )}

      {/* Column visibility */}
      <ColumnVisibilityDropdown table={table} />
    </div>
  )
}

/**
 * Faceted filter button: click to open a popover with multi-select checkboxes.
 */
function FacetedFilterButton({ column, title, options }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef(null)

  if (!column) return null

  const filterValue = column.getFilterValue()
  const selected = Array.isArray(filterValue) ? filterValue : []

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const filteredOptions = search
    ? options.filter((o) =>
        o.label.toLowerCase().includes(search.toLowerCase()),
      )
    : options

  const toggleValue = (value) => {
    const next = selected.includes(value)
      ? selected.filter((v) => v !== value)
      : [...selected, value]
    column.setFilterValue(next.length > 0 ? next : undefined)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => {
          setOpen(!open)
          setSearch('')
        }}
        className={cn(
          'inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs transition-colors',
          selected.length > 0
            ? 'border-brand-300 bg-brand-50 text-brand-700'
            : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 hover:text-gray-900',
        )}
      >
        <Filter className="h-3.5 w-3.5" />
        {title}
        {selected.length > 0 && (
          <span className="ml-1 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-brand-600 px-1 text-[10px] font-medium text-white">
            {selected.length}
          </span>
        )}
        <ChevronDown className="h-3 w-3" />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-40 mt-1 w-56 rounded-md border border-gray-200 bg-white p-2 shadow-lg">
          {/* Search */}
          <div className="relative mb-2">
            <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder={`Search ${title.toLowerCase()}...`}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-md border border-gray-200 bg-white py-1 pl-7 pr-2 text-xs outline-none placeholder:text-gray-400 focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
              autoFocus
            />
          </div>

          {/* Select All / Clear */}
          <div className="mb-1 flex items-center justify-between px-1">
            <button
              onClick={() => {
                const allValues = filteredOptions.map((o) => o.value)
                column.setFilterValue(allValues.length > 0 ? allValues : undefined)
              }}
              className="text-[10px] text-brand-600 hover:underline"
            >
              Select all
            </button>
            {selected.length > 0 && (
              <button
                onClick={() => column.setFilterValue(undefined)}
                className="text-[10px] text-gray-500 hover:text-gray-700"
              >
                Clear
              </button>
            )}
          </div>

          {/* Options */}
          <div className="max-h-48 space-y-0.5 overflow-y-auto">
            {filteredOptions.length === 0 ? (
              <p className="py-2 text-center text-xs text-gray-500">
                No options
              </p>
            ) : (
              filteredOptions.map((option) => {
                const checked = selected.includes(option.value)
                return (
                  <label
                    key={option.value}
                    className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-xs hover:bg-gray-50"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleValue(option.value)}
                      className="h-3.5 w-3.5 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
                    />
                    <span className="truncate">{option.label}</span>
                  </label>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Column visibility dropdown.
 */
function ColumnVisibilityDropdown({ table }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex h-8 items-center gap-1.5 rounded-md border border-gray-200 bg-white px-2.5 text-xs text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900"
      >
        <Eye className="h-3.5 w-3.5" />
        Columns
      </button>

      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-48 rounded-md border border-gray-200 bg-white p-2 shadow-lg">
          <p className="mb-1 px-1 text-xs font-medium text-gray-500">
            Toggle columns
          </p>
          {table.getAllLeafColumns().map((column) => {
            if (!column.getCanHide()) return null
            return (
              <label
                key={column.id}
                className="flex items-center gap-2 rounded px-1 py-1 text-xs hover:bg-gray-50"
              >
                <input
                  type="checkbox"
                  checked={column.getIsVisible()}
                  onChange={column.getToggleVisibilityHandler()}
                  className="h-3.5 w-3.5 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
                />
                <span className="truncate capitalize">
                  {typeof column.columnDef.header === 'string'
                    ? column.columnDef.header
                    : column.id.replace(/_/g, ' ')}
                </span>
              </label>
            )
          })}
        </div>
      )}
    </div>
  )
}
