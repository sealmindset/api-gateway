'use client'

import { useState, useRef, useEffect } from 'react'
import {
  ArrowUp,
  ArrowDown,
  ChevronsUpDown,
  Filter,
  Search,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'

export function DataTableColumnHeader({ column, title, className }) {
  const [showFilter, setShowFilter] = useState(false)
  const filterRef = useRef(null)

  // Close filter dropdown on outside click
  useEffect(() => {
    if (!showFilter) return
    const handler = (e) => {
      if (filterRef.current && !filterRef.current.contains(e.target)) {
        setShowFilter(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showFilter])

  if (!column.getCanSort() && !column.getCanFilter()) {
    return <div className={className}>{title}</div>
  }

  const sorted = column.getIsSorted()
  const isFiltered = column.getIsFiltered()

  return (
    <div className={cn('relative flex items-center gap-1', className)}>
      {/* Sort toggle */}
      {column.getCanSort() ? (
        <button
          onClick={() => column.toggleSorting()}
          className="-ml-1 flex items-center gap-1 rounded px-1 py-0.5 transition-colors hover:bg-gray-100"
        >
          <span className="select-none">{title}</span>
          {sorted === 'asc' ? (
            <ArrowUp className="h-3.5 w-3.5" />
          ) : sorted === 'desc' ? (
            <ArrowDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronsUpDown className="h-3.5 w-3.5 text-gray-400" />
          )}
        </button>
      ) : (
        <span>{title}</span>
      )}

      {/* Filter trigger */}
      {column.getCanFilter() && (
        <button
          onClick={() => setShowFilter(!showFilter)}
          className={cn(
            'rounded p-0.5 transition-colors hover:bg-gray-100',
            isFiltered && 'text-brand-600',
          )}
          title={`Filter ${title}`}
        >
          <Filter
            className={cn('h-3 w-3', isFiltered ? 'fill-brand-600/20' : '')}
          />
        </button>
      )}

      {/* Excel-like filter dropdown */}
      {showFilter && column.getCanFilter() && (
        <div
          ref={filterRef}
          className="absolute left-0 top-full z-40 mt-1 w-60 rounded-md border border-gray-200 bg-white p-3 shadow-lg"
        >
          <ExcelColumnFilter column={column} title={title} />
        </div>
      )}
    </div>
  )
}

/**
 * Excel-like column filter popup:
 * - Search box to filter the value list
 * - Select All / Clear All buttons
 * - Scrollable list of checkboxes with unique values
 * - Count indicator
 */
function ExcelColumnFilter({ column, title }) {
  const [search, setSearch] = useState('')
  const filterValue = column.getFilterValue()

  // Get unique values from the faceted model
  const facetedValues = column.getFacetedUniqueValues()
  const allValues = Array.from(facetedValues.keys())
    .map(String)
    .filter(Boolean)
    .sort()

  // Filter the value list by search term
  const filteredValues = search
    ? allValues.filter((v) => v.toLowerCase().includes(search.toLowerCase()))
    : allValues

  // Current selection (array of selected values)
  const selected = Array.isArray(filterValue) ? filterValue : []
  const isActive = selected.length > 0

  const toggleValue = (value) => {
    const next = selected.includes(value)
      ? selected.filter((v) => v !== value)
      : [...selected, value]
    column.setFilterValue(next.length > 0 ? next : undefined)
  }

  const selectAll = () => {
    column.setFilterValue(
      filteredValues.length > 0 ? [...filteredValues] : undefined,
    )
  }

  const clearAll = () => {
    column.setFilterValue(undefined)
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-gray-500">
        Filter: {title}
      </p>

      {/* Search box */}
      <div className="relative">
        <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          placeholder="Search values..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-md border border-gray-200 bg-white py-1 pl-7 pr-2 text-xs outline-none placeholder:text-gray-400 focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
          autoFocus
        />
      </div>

      {/* Select All / Clear All */}
      <div className="flex items-center justify-between">
        <button
          onClick={selectAll}
          className="text-xs text-brand-600 hover:underline"
        >
          Select all ({filteredValues.length})
        </button>
        {isActive && (
          <button
            onClick={clearAll}
            className="inline-flex items-center gap-0.5 text-xs text-gray-500 hover:text-gray-700"
          >
            <X className="h-3 w-3" />
            Clear
          </button>
        )}
      </div>

      {/* Checkbox list */}
      <div className="max-h-48 space-y-0.5 overflow-y-auto">
        {filteredValues.length === 0 ? (
          <p className="py-2 text-center text-xs text-gray-500">
            No values found
          </p>
        ) : (
          filteredValues.map((value) => {
            const count = facetedValues.get(value) ?? 0
            const checked = selected.includes(value)
            return (
              <label
                key={value}
                className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-xs hover:bg-gray-50"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleValue(value)}
                  className="h-3.5 w-3.5 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
                />
                <span className="flex-1 truncate">{value}</span>
                <span className="text-gray-400">{count}</span>
              </label>
            )
          })
        )}
      </div>

      {/* Active filter indicator */}
      {isActive && (
        <p className="text-xs text-brand-600">
          {selected.length} of {allValues.length} selected
        </p>
      )}
    </div>
  )
}
