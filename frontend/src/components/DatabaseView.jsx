import { useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, Database, Download, LoaderCircle, Package, Search, Users } from 'lucide-react'
import { api } from '../lib/api'

const tables = {
  orders: 'Đơn hàng', customers: 'Khách hàng', products: 'Sản phẩm',
  order_items: 'Chi tiết đơn hàng', payments: 'Thanh toán', returns: 'Trả hàng',
}
const labels = {
  order_id: 'Mã đơn', customer_id: 'Mã khách', customer_name: 'Khách hàng', full_name: 'Họ tên',
  email: 'Email', city: 'Thành phố', product_id: 'Mã sản phẩm', name: 'Tên sản phẩm', category: 'Danh mục',
  ordered_at: 'Ngày đặt', delivered_at: 'Ngày giao', status: 'Trạng thái', shipping_region: 'Vùng giao',
  membership_at_purchase: 'Hạng lúc mua', merchandise_total_vnd: 'Tiền hàng (VND)', shipping_fee_vnd: 'Phí giao (VND)',
  list_price_vnd: 'Giá niêm yết (VND)', order_item_id: 'Mã dòng hàng', quantity: 'Số lượng',
  unit_price_vnd: 'Đơn giá (VND)', discount_vnd: 'Giảm giá dòng (VND)', is_clearance: 'Thanh lý',
  payment_id: 'Mã thanh toán', paid_at: 'Ngày thanh toán', amount_vnd: 'Số tiền (VND)', method: 'Phương thức',
  return_id: 'Mã trả hàng', requested_at: 'Ngày yêu cầu', reason: 'Lý do', item_condition: 'Tình trạng hàng',
  refunded_at: 'Ngày hoàn tiền', refund_amount_vnd: 'Tiền hoàn (VND)',
}
const statuses = {
  delivered: 'Đã giao', cancelled: 'Đã hủy', pending: 'Chờ xử lý', succeeded: 'Thành công',
  failed: 'Thất bại', requested: 'Đã yêu cầu', rejected: 'Từ chối', refunded: 'Đã hoàn tiền',
}
function formatValue(column, value) {
  if (value == null) return 'NULL'
  if (column === 'status') return statuses[value] || value
  if (column === 'is_clearance') return value ? 'Có' : 'Không'
  if (column.endsWith('_vnd')) return value.toLocaleString('vi-VN')
  return String(value)
}

export default function DatabaseView() {
  const [data, setData] = useState(null)
  const [table, setTable] = useState('orders')
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => { setQuery(search); setPage(1) }, 300)
    return () => clearTimeout(timer)
  }, [search, table])
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setLoading(true); setError('')
    api.database({ page, search: query, table }, controller.signal).then((next) => { if (active) setData(next) })
      .catch((err) => { if (active) setError(err.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false; controller.abort() }
  }, [page, query, table])

  function selectTable(event) {
    setTable(event.target.value); setPage(1); setSearch(''); setQuery(''); setData(null)
  }

  function download() {
    const csv = [data.columns.join(','), ...data.rows.map((row) => data.columns.map((column) => `"${String(row[column] ?? '').replaceAll('"', '""')}"`).join(','))].join('\n')
    const url = URL.createObjectURL(new Blob(['\ufeff', csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = `${data.table}_page_${page}.csv`; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <section className="database-view"><div className="database-intro"><span className="eyebrow">STRUCTURED DATA</span><h1>Khám phá dữ liệu</h1><p>Xem 6 bảng dữ liệu bán hàng giả lập. NULL là thông tin chưa có; các khoản tiền tính bằng VND.</p></div>
    <div className="stat-grid">{[
      { icon: Database, label: query ? 'Bản ghi phù hợp' : tables[table], value: data?.total },
      { icon: Users, label: 'Khách hàng trong dataset', value: data?.total_customers },
      { icon: Package, label: 'Sản phẩm trong dataset', value: data?.total_products },
    ].map(({ icon: Icon, label, value }) => <div className="stat-card" key={label}><span><Icon size={18} />{label}</span><strong>{value == null ? '—' : value.toLocaleString('vi-VN')}</strong></div>)}</div>
    <div className="database-table-card"><div className="table-toolbar"><div><Database size={17} /><select aria-label="Chọn bảng dữ liệu" value={table} onChange={selectTable}>{Object.entries(tables).map(([name, label]) => <option key={name} value={name}>{label} · {name}</option>)}</select><span>SQLite</span></div><button className="button secondary" onClick={download} disabled={!data?.rows.length || loading || !!error}><Download size={15} />Xuất trang này</button></div>
      <div className="table-search"><Search size={17} /><input aria-label="Tìm trong bảng" placeholder={`Tìm trong ${tables[table].toLowerCase()}…`} value={search} onChange={(event) => setSearch(event.target.value)} /></div>
      {table === 'orders' && <p className="table-note">Tiền hàng sau giảm giá, chưa trừ hoàn tiền và chưa cộng phí giao hàng.</p>}
      {error ? <div className="table-empty" role="alert">{error}</div> : loading ? <div className="table-empty"><LoaderCircle size={22} className="spin" />Đang tải dữ liệu…</div> : <div className="table-overflow"><table><thead><tr>{data?.columns.map((column) => <th key={column} title={column}>{labels[column] || column}</th>)}</tr></thead><tbody>{data?.rows.map((row) => <tr key={row[data.columns[0]]}>{data.columns.map((column) => <td key={column} className={typeof row[column] === 'number' ? 'numeric' : undefined}>{formatValue(column, row[column])}</td>)}</tr>)}</tbody></table>{!data?.rows.length && <div className="table-empty">Không có bản ghi phù hợp.</div>}</div>}
      <div className="pagination"><span>{data ? `${data.total} kết quả · Trang ${page}/${Math.max(1, Math.ceil(data.total / data.page_size))}` : '—'}</span><div><button className="icon-button" aria-label="Trang trước" disabled={page <= 1 || loading || !!error} onClick={() => setPage(page - 1)}><ArrowLeft size={17} /></button><button className="icon-button" aria-label="Trang sau" disabled={!data || page * data.page_size >= data.total || loading || !!error} onClick={() => setPage(page + 1)}><ArrowRight size={17} /></button></div></div>
    </div>
  </section>
}
