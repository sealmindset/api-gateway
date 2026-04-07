'use client'

import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'
import { cn } from '@/lib/utils'

export function DataTablePagination({ table }) {
  const pageCount = table.getPageCount()
  const pageIndex = table.getState().pagination.pageIndex
  const totalRows = table.getFilteredRowModel().rows.length

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border px-4 py-3 text-sm">
      {/* Total rows */}
      <div className="text-xs text-muted-foreground">
        {totalRows} row{totalRows !== 1 ? 's' : ''} total
      </div>

      <div className="flex items-center gap-4">
        {/* Page size selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Rows per page</span>
          <select
            value={table.getState().pagination.pageSize}
            onChange={(e) => table.setPageSize(Number(e.target.value))}
            className="rounded-md border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {[10, 20, 50, 100].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>

        {/* Page indicator */}
        <span className="text-xs text-muted-foreground">
          Page {pageIndex + 1} of {pageCount || 1}
        </span>

        {/* Navigation buttons */}
        <div className="flex items-center gap-1">
          <NavButton
            onClick={() => table.setPageIndex(0)}
            disabled={!table.getCanPreviousPage()}
            title="First page"
          >
            <ChevronsLeft className="h-4 w-4" />
          </NavButton>
          <NavButton
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
            title="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </NavButton>
          <NavButton
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
            title="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </NavButton>
          <NavButton
            onClick={() => table.setPageIndex(pageCount - 1)}
            disabled={!table.getCanNextPage()}
            title="Last page"
          >
            <ChevronsRight className="h-4 w-4" />
          </NavButton>
        </div>
      </div>
    </div>
  )
}

function NavButton({ onClick, disabled, title, children }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        'inline-flex h-8 w-8 items-center justify-center rounded-md border border-input transition-colors',
        disabled
          ? 'opacity-50 cursor-not-allowed'
          : 'hover:bg-accent hover:text-accent-foreground',
      )}
    >
      {children}
    </button>
  )
}
