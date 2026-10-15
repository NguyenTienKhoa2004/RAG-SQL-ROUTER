import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { api } from './lib/api'

vi.mock('./lib/api', () => ({ api: {
  health: vi.fn(), connect: vi.fn(), session: vi.fn(), chat: vi.fn(),
  upload: vi.fn(), reset: vi.fn(), disconnect: vi.fn(), database: vi.fn(),
} }))

const emptySession = () => ({ id: 'workspace-test', model: 'qwen/test', documents: [], messages: [], available_tools: ['sql_tool'] })

beforeEach(() => {
  vi.resetAllMocks()
  api.health.mockResolvedValue({ database_available: true, server_key_configured: false, max_upload_bytes: 20971520 })
  api.session.mockResolvedValue(emptySession())
  api.connect.mockResolvedValue(emptySession())
})

async function connectedApp() {
  sessionStorage.setItem('forma-session', 'workspace-test')
  render(<App />)
  await screen.findByRole('button', { name: 'Đã kết nối' })
  return userEvent.setup()
}

describe('Workspace interactions', () => {
  it('renders the sales database contract and searches orders', async () => {
    api.database.mockResolvedValue({ table: 'orders', columns: ['order_id', 'customer_id', 'customer_name', 'ordered_at', 'status', 'merchandise_total_vnd', 'shipping_fee_vnd'], total: 1,
      total_customers: 120, total_products: 12, page: 1, page_size: 20,
      rows: [{ order_id: 'DH1004', customer_id: 'KH004', customer_name: 'Khách mẫu 004',
        ordered_at: '2026-09-10', status: 'delivered', merchandise_total_vnd: 690000, shipping_fee_vnd: 0 }],
    })
    const user = await connectedApp()
    await user.click(screen.getByRole('button', { name: 'Cơ sở dữ liệu' }))
    await screen.findByText('DH1004')
    expect(screen.getByText('690.000')).toBeTruthy()
    expect(screen.getByText('Đã giao')).toBeTruthy()
    await user.type(screen.getByRole('textbox', { name: 'Tìm trong bảng' }), 'DH1004')
    await waitFor(() => expect(api.database).toHaveBeenLastCalledWith(
      { page: 1, search: 'DH1004', table: 'orders' }, expect.any(AbortSignal)))
  })

  it('switches between all six tables and resets pagination and search', async () => {
    const records = {
      orders: { order_id: 'DH1005', delivered_at: null },
      customers: { customer_id: 'KH001', full_name: 'Nguyễn Văn An' },
      products: { product_id: 'SP01', list_price_vnd: 200000 },
      order_items: { order_item_id: 1, discount_vnd: 0 },
      payments: { payment_id: 1, status: 'failed' },
      returns: { return_id: 1, refunded_at: null },
    }
    api.database.mockImplementation(async ({ table, page }) => ({
      table, page, columns: Object.keys(records[table]), rows: [records[table]],
      total: 40, page_size: 20, total_customers: 120, total_products: 12,
    }))
    const user = await connectedApp()
    await user.click(screen.getByRole('button', { name: 'Cơ sở dữ liệu' }))
    await screen.findByText('DH1005')
    expect(screen.getByText('NULL')).toBeTruthy()
    await user.type(screen.getByRole('textbox', { name: 'Tìm trong bảng' }), 'DH1005')
    await waitFor(() => expect(api.database).toHaveBeenLastCalledWith(
      { table: 'orders', page: 1, search: 'DH1005' }, expect.any(AbortSignal)))
    await user.click(screen.getByRole('button', { name: 'Trang sau' }))
    await waitFor(() => expect(api.database).toHaveBeenLastCalledWith(
      { table: 'orders', page: 2, search: 'DH1005' }, expect.any(AbortSignal)))
    const selector = screen.getByRole('combobox', { name: 'Chọn bảng dữ liệu' })
    expect(within(selector).getAllByRole('option')).toHaveLength(6)
    for (const table of ['customers', 'products', 'order_items', 'payments', 'returns']) {
      await user.selectOptions(selector, table)
      await waitFor(() => expect(api.database).toHaveBeenLastCalledWith(
        { table, page: 1, search: '' }, expect.any(AbortSignal)))
      expect(screen.getByRole('textbox', { name: 'Tìm trong bảng' }).value).toBe('')
      const grid = await screen.findByRole('table')
      expect(within(grid).getAllByRole('columnheader')).toHaveLength(2)
      expect(screen.queryByText('DH1005')).toBeNull()
    }
    expect(screen.getByText('NULL')).toBeTruthy()
  })

  it('connects through the dialog, stores only a session id and clears the API key', async () => {
    const user = userEvent.setup()
    render(<App />)
    const connectButton = screen.getByRole('button', { name: 'Kết nối workspace' })
    await waitFor(() => expect(connectButton.disabled).toBe(false))
    await user.click(connectButton)
    const input = screen.getByLabelText('OpenRouter API key')
    await user.type(input, 'private-key-for-test')
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Kết nối workspace', exact: true }))
    await screen.findByRole('button', { name: 'Đã kết nối' })
    expect(api.connect).toHaveBeenCalledWith('private-key-for-test')
    expect(sessionStorage.getItem('forma-session')).toBe('workspace-test')
    await waitFor(() => expect(screen.queryByLabelText('OpenRouter API key')).toBeNull())
    expect(JSON.stringify(sessionStorage)).not.toContain('private-key-for-test')
  })

  it('displays the final answer, preserves follow-up turns and exposes tool details', async () => {
    const user = await connectedApp()
    api.chat.mockResolvedValueOnce({ id: 'a1', role: 'assistant', content: 'Chicago có 2.746.388 người.', tools: [{ name: 'sql_tool', content: 'Raw Chicago population' }], duration_ms: 150 })
    api.chat.mockResolvedValueOnce({ id: 'a2', role: 'assistant', content: 'Chicago thuộc bang Illinois.', tools: [{ name: 'sql_tool', content: 'Illinois' }] })
    const input = screen.getByRole('textbox', { name: 'Câu hỏi của bạn' })
    await user.type(input, 'Dân số Chicago?{Enter}')
    await screen.findByText('Chicago có 2.746.388 người.')
    await user.type(input, 'Thành phố đó thuộc bang nào?{Enter}')
    await screen.findByText('Chicago thuộc bang Illinois.')
    expect(screen.getByText('Chicago có 2.746.388 người.')).toBeTruthy()
    expect(api.chat).toHaveBeenLastCalledWith('workspace-test', 'Thành phố đó thuộc bang nào?')
    await user.click(screen.getAllByText('Xem kết quả tra cứu')[0])
    expect(screen.getByText('Raw Chicago population')).toBeTruthy()
  })

  it('restores the draft after a failed query and allows retry', async () => {
    const user = await connectedApp()
    api.chat.mockRejectedValueOnce(new Error('OpenRouter unavailable'))
    const input = screen.getByRole('textbox', { name: 'Câu hỏi của bạn' })
    await user.type(input, 'Chicago?{Enter}')
    await screen.findByRole('alert')
    await waitFor(() => expect(input.value).toBe('Chicago?'))
    expect(screen.getByRole('alert').textContent).toContain('OpenRouter unavailable')
    expect(screen.getByRole('button', { name: 'Gửi câu hỏi' }).disabled).toBe(false)
  })

  it('uploads documents and starts a new conversation without removing the files', async () => {
    const user = await connectedApp()
    const document = { name: 'policy.txt', size: 10 }
    api.upload.mockResolvedValue({ ...emptySession(), documents: [document], available_tools: ['sql_tool', 'document_tool'] })
    api.reset.mockResolvedValue({ ...emptySession(), documents: [document] })
    const file = new File(['Policy text'], 'policy.txt', { type: 'text/plain' })
    await user.upload(screen.getByLabelText('Chọn tài liệu'), file)
    await screen.findByText('policy.txt')
    expect(api.upload).toHaveBeenCalledWith('workspace-test', [file])
    await user.click(screen.getByRole('button', { name: 'Cuộc trò chuyện mới' }))
    await waitFor(() => expect(api.reset).toHaveBeenCalledWith('workspace-test'))
    expect(screen.getByText('policy.txt')).toBeTruthy()
  })

  it('clears an expired session and invites the user to reconnect', async () => {
    sessionStorage.setItem('forma-session', 'expired')
    api.session.mockRejectedValue(Object.assign(new Error('Expired'), { status: 404 }))
    render(<App />)
    await waitFor(() => expect(sessionStorage.getItem('forma-session')).toBeNull())
    expect(screen.getByRole('button', { name: 'Kết nối workspace' })).toBeTruthy()
  })
})
