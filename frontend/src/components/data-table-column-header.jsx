'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
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
  const [dropdownPos, setDropdownPos] = useState({ top: 0, left: 0 })
  const filterBtnRef = useRef(null)
  const filterRef = useRef(null)

  // Calculate fixed position from the trigger button's bounding rect
  const openFilter = useCallback(() => {
    if (filterBtnRef.current) {
      const rect = filterBtnRef.current.getBoundingClientRect()
      setDropdownPos({
        top: rect.bottom + 4,
        left: rect.left,
      })
    }
    setShowFilter(true)
  }, [])

  // Close filter dropdown on outside click
  useEffect(() => {
    if (!showFilter) return
    const handler = (e) => {
      if (
        filterRef.current &&
        !filterRef.current.contains(e.target) &&
        filterBtnRef.current &&
        !filterBtnRef.current.contains(e.target)
      ) {
        setShowFilter(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showFilter])

  // Reposition on scroll/resize while open
  useEffect(() => {
    if (!showFilter || !filterBtnRef.current) return
    const reposition = () => {
      if (filterBtnRef.current) {
        const rect = filterBtnRef.current.getBoundingClientRect()
        setDropdownPos({
          top: rect.bottom + 4,
          left: rect.left,
        })
      }
    }
    window.addEventListener('scroll', reposition, true)
    window.addEventListener('resize', reposition)
    return () => {
      window.removeEventListener('scroll', reposition, true)
      window.removeEventListener('resize', reposition)
    }
  }, [showFilter])

  if (!column.getCanSort() && !column.getCanFilter()) {
    return <div className={className}>{title}</div>
  }

  const sorted = column.getIsSorted()
  const isFiltered = column.getIsFiltered()

  return (
    <div className={cn('flex items-center gap-1', className)}>
      {/* Sort toggle */}
      {column.getCanSort() ? (
        <button
          onClick={() => column.toggleSorting()}
          className="-ml-1 flex items-center gap-1 rounded px-1 py-0.5 transition-colors hover:bg-accent"
        >
          <span className="select-none">{title}</span>
          {sorted === 'asc' ? (
            <ArrowUp className="h-3.5 w-3.5" />
          ) : sorted === 'desc' ? (
            <ArrowDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground/50" />
          )}
        </button>
      ) : (
        <span>{title}</span>
      )}

      {/* Filter trigger */}
      {column.getCanFilter() && (
        <button
          ref={filterBtnRef}
          onClick={() => (showFilter ? setShowFilter(false) : openFilter())}
          className={cn(
            'rounded p-0.5 transition-colors hover:bg-accent',
            isFiltered && 'text-primary',
          )}
          title={`Filter ${title}`}
        >
          <Filter
            className={cn('h-3 w-3', isFiltered ? 'fill-primary/20' : '')}
          />
        </button>
      )}

      {/* Excel-like filter dropdown -- uses position:fixed to escape overflow clipping */}
      {showFilter && column.getCanFilter() && (
        <div
          ref={filterRef}
          className="fixed z-50 w-60 rounded-md border border-border bg-card p-3 shadow-lg"
          style={{
            top: dropdownPos.top,
            left: dropdownPos.left,
          }}
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
      <p className="text-xs font-medium text-muted-foreground">
        Filter: {title}
      </p>

      {/* Search box */}
      <div className="relative">
        <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search values..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-md border border-input bg-background py-1 pl-7 pr-2 text-xs outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
          autoFocus
        />
      </div>

      {/* Select All / Clear All */}
      <div className="flex items-center justify-between">
        <button
          onClick={selectAll}
          className="text-xs text-primary hover:underline"
        >
          Select all ({filteredValues.length})
        </button>
        {isActive && (
          <button
            onClick={clearAll}
            className="inline-flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground"
          >
            <X className="h-3 w-3" />
            Clear
          </button>
        )}
      </div>

      {/* Checkbox list */}
      <div className="max-h-48 space-y-0.5 overflow-y-auto">
        {filteredValues.length === 0 ? (
          <p className="py-2 text-center text-xs text-muted-foreground">
            No values found
          </p>
        ) : (
          filteredValues.map((value) => {
            const count = facetedValues.get(value) ?? 0
            const checked = selected.includes(value)
            return (
              <label
                key={value}
                className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-xs hover:bg-accent/50"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleValue(value)}
                  className="h-3.5 w-3.5 rounded border-input text-primary focus:ring-ring"
                />
                <span className="flex-1 truncate">{value}</span>
                <span className="text-muted-foreground">{count}</span>
              </label>
            )
          })
        )}
      </div>

      {/* Active filter indicator */}
      {isActive && (
        <p className="text-xs text-primary">
          {selected.length} of {allValues.length} selected
        </p>
      )}
    </div>
  )
}
