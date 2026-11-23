import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataTable } from '../components/tables/DataTable'

const columns = [
  { key: 'symbol', header: 'Symbol' },
  { key: 'pnl', header: 'P&L', align: 'right', numeric: true },
]

const rows = [
  { id: 1, symbol: 'ALPHA', pnl: 300 },
  { id: 2, symbol: 'BETA', pnl: -100 },
  { id: 3, symbol: 'GAMMA', pnl: 50 },
]

describe('DataTable', () => {
  it('renders every row', () => {
    render(<DataTable columns={columns} rows={rows} />)
    expect(screen.getByText('ALPHA')).toBeInTheDocument()
    expect(screen.getByText('GAMMA')).toBeInTheDocument()
    expect(screen.getByText('3 rows')).toBeInTheDocument()
  })

  it('filters on search', async () => {
    const user = userEvent.setup()
    render(<DataTable columns={columns} rows={rows} />)
    await user.type(screen.getByLabelText('Search table'), 'BET')
    expect(screen.getByText('BETA')).toBeInTheDocument()
    expect(screen.queryByText('ALPHA')).not.toBeInTheDocument()
  })

  it('sorts ascending then descending', async () => {
    const user = userEvent.setup()
    render(<DataTable columns={columns} rows={rows} />)
    const header = screen.getByRole('button', { name: /P&L/ })

    await user.click(header)
    let cells = screen.getAllByRole('row').slice(1).map((r) => r.cells[0].textContent)
    expect(cells).toEqual(['BETA', 'GAMMA', 'ALPHA'])

    await user.click(header)
    cells = screen.getAllByRole('row').slice(1).map((r) => r.cells[0].textContent)
    expect(cells).toEqual(['ALPHA', 'GAMMA', 'BETA'])
  })

  it('shows an empty state rather than a bare table', () => {
    render(<DataTable columns={columns} rows={[]} emptyTitle="Nothing here" />)
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })

  it('shows a loading state', () => {
    render(<DataTable columns={columns} rows={[]} loading />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('paginates locally', async () => {
    const user = userEvent.setup()
    const many = Array.from({ length: 30 }, (_, i) => ({
      id: i,
      symbol: `SYM${i}`,
      pnl: i,
    }))
    render(<DataTable columns={columns} rows={many} pageSize={10} />)
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
    expect(screen.queryByText('SYM15')).not.toBeInTheDocument()

    await user.click(screen.getByLabelText('Next page'))
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
    expect(screen.getByText('SYM15')).toBeInTheDocument()
  })
})
