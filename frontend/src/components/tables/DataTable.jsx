import { useMemo, useState } from 'react'
import clsx from 'clsx'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Download, Search } from 'lucide-react'
import { EmptyState, Loading } from '../ui'

/**
 * One table component for the whole app: search, sort, pagination and CSV
 * export in a single place, so every table behaves the same way.
 *
 * Server-side pagination is used when `page`/`onPageChange` are supplied;
 * otherwise it paginates in the browser.
 */
export function DataTable({
  columns,
  rows,
  loading,
  emptyTitle = 'Nothing to show',
  emptyDescription,
  searchable = true,
  searchPlaceholder = 'Search…',
  pageSize = 25,
  page,
  total,
  onPageChange,
  exportName,
  rowKey = (row, i) => row.id ?? i,
  onRowClick,
  dense = false,
}) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState(null)
  const [localPage, setLocalPage] = useState(1)

  const serverPaged = typeof page === 'number' && typeof onPageChange === 'function'

  const filtered = useMemo(() => {
    if (!searchable || !query.trim()) return rows ?? []
    const q = query.toLowerCase()
    return (rows ?? []).filter((row) =>
      columns.some((col) => {
        const value = col.value ? col.value(row) : row[col.key]
        return value != null && String(value).toLowerCase().includes(q)
      }),
    )
  }, [rows, query, columns, searchable])

  const sorted = useMemo(() => {
    if (!sort) return filtered
    const col = columns.find((c) => c.key === sort.key)
    if (!col) return filtered
    const get = (row) => (col.value ? col.value(row) : row[col.key])
    return [...filtered].sort((a, b) => {
      const av = get(a)
      const bv = get(b)
      if (av == null) return 1
      if (bv == null) return -1
      const cmp =
        typeof av === 'number' && typeof bv === 'number'
          ? av - bv
          : String(av).localeCompare(String(bv), undefined, { numeric: true })
      return sort.dir === 'asc' ? cmp : -cmp
    })
  }, [filtered, sort, columns])

  const pageRows = serverPaged
    ? sorted
    : sorted.slice((localPage - 1) * pageSize, localPage * pageSize)

  const currentPage = serverPaged ? page : localPage
  const totalRows = serverPaged ? (total ?? 0) : sorted.length
  const totalPages = Math.max(Math.ceil(totalRows / pageSize), 1)

  const setPage = (next) => {
    const clamped = Math.min(Math.max(next, 1), totalPages)
    if (serverPaged) onPageChange(clamped)
    else setLocalPage(clamped)
  }

  const toggleSort = (key) =>
    setSort((prev) =>
      prev?.key === key
        ? prev.dir === 'asc'
          ? { key, dir: 'desc' }
          : null
        : { key, dir: 'asc' },
    )

  const exportCsv = () => {
    const header = columns.map((c) => `"${c.header}"`).join(',')
    const body = sorted
      .map((row) =>
        columns
          .map((c) => {
            const v = c.value ? c.value(row) : row[c.key]
            return `"${String(v ?? '').replace(/"/g, '""')}"`
          })
          .join(','),
      )
      .join('\n')
    const blob = new Blob([`${header}\n${body}`], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${exportName}-${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-col">
      {(searchable || exportName) && (
        <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-b border-base-700">
          {searchable && (
            <div className="relative flex-1 min-w-[180px] max-w-sm">
              <Search
                size={13}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint"
              />
              <input
                className="input pl-8 py-1"
                placeholder={searchPlaceholder}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value)
                  setLocalPage(1)
                }}
                aria-label="Search table"
              />
            </div>
          )}
          <span className="text-2xs text-ink-faint tnum ml-auto">
            {totalRows.toLocaleString('en-IN')} {totalRows === 1 ? 'row' : 'rows'}
          </span>
          {exportName && sorted.length > 0 && (
            <button type="button" className="btn-ghost py-1" onClick={exportCsv}>
              <Download size={12} /> CSV
            </button>
          )}
        </div>
      )}

      {loading ? (
        <Loading />
      ) : pageRows.length === 0 ? (
        <EmptyState title={emptyTitle} description={emptyDescription} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead className="bg-base-800 sticky top-0 z-10">
              <tr>
                {columns.map((col) => (
                  <th
                    key={col.key}
                    className={clsx('th', col.align === 'right' && 'text-right', col.thClass)}
                  >
                    {col.sortable === false ? (
                      col.header
                    ) : (
                      <button
                        type="button"
                        onClick={() => toggleSort(col.key)}
                        className="inline-flex items-center gap-1 hover:text-ink transition-colors"
                      >
                        {col.header}
                        {sort?.key === col.key &&
                          (sort.dir === 'asc' ? <ArrowUp size={10} /> : <ArrowDown size={10} />)}
                      </button>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row, i) => (
                <tr
                  key={rowKey(row, i)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={clsx(
                    'border-t border-base-700/60 transition-colors',
                    onRowClick && 'cursor-pointer hover:bg-base-800',
                    dense && 'text-xs',
                  )}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={clsx(
                        'td',
                        col.align === 'right' && 'text-right',
                        col.numeric && 'tnum font-mono text-xs',
                        col.tdClass,
                      )}
                    >
                      {col.render ? col.render(row) : (row[col.key] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-base-700">
          <span className="text-2xs text-ink-faint tnum">
            Page {currentPage} of {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="btn-ghost p-1.5"
              disabled={currentPage <= 1}
              onClick={() => setPage(currentPage - 1)}
              aria-label="Previous page"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              type="button"
              className="btn-ghost p-1.5"
              disabled={currentPage >= totalPages}
              onClick={() => setPage(currentPage + 1)}
              aria-label="Next page"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
