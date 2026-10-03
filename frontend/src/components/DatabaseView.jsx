import { useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, Database, Download, LoaderCircle, MapPin, Search, Users } from 'lucide-react'
import { api } from '../lib/api'

export default function DatabaseView() {
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => { setQuery(search); setPage(1) }, 300)
    return () => clearTimeout(timer)
  }, [search])
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setLoading(true); setError('')
    api.database({ page, search: query }, controller.signal).then((next) => { if (active) setData(next) })
      .catch((err) => { if (active) setError(err.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false; controller.abort() }
  }, [page, query])

  function download() {
    const csv = ['city_name,population,state', ...data.rows.map((row) => [row.city_name, row.population, row.state].map((value) => `"${String(value).replaceAll('"', '""')}"`).join(','))].join('\n')
    const url = URL.createObjectURL(new Blob(['\ufeff', csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = `city_stats_page_${page}.csv`; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <section className="database-view"><div className="database-intro"><span className="eyebrow">STRUCTURED DATA</span><h1>Khám phá dữ liệu</h1><p>Xem dữ liệu thành phố mà trợ lý sử dụng để trả lời.</p></div>
    <div className="stat-grid">{[
      { icon: Database, label: query ? 'Thành phố phù hợp' : 'Thành phố', value: data?.total },
      { icon: Users, label: 'Tổng dân số dataset', value: data?.total_population },
      { icon: MapPin, label: 'Bang trong dataset', value: data?.states },
    ].map(({ icon: Icon, label, value }) => <div className="stat-card" key={label}><span><Icon size={18} />{label}</span><strong>{value == null ? '—' : value.toLocaleString('vi-VN')}</strong></div>)}</div>
    <div className="database-table-card"><div className="table-toolbar"><div><Database size={17} /><strong>city_stats</strong><span>SQLite</span></div><button className="button secondary" onClick={download} disabled={!data?.rows.length || loading || !!error}><Download size={15} />Xuất trang này</button></div>
      <div className="table-search"><Search size={17} /><input aria-label="Tìm thành phố hoặc bang" placeholder="Tìm thành phố hoặc bang…" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
      {error ? <div className="table-empty" role="alert">{error}</div> : loading ? <div className="table-empty"><LoaderCircle size={22} className="spin" />Đang tải dữ liệu…</div> : <div className="table-overflow"><table><thead><tr><th>THÀNH PHỐ</th><th>DÂN SỐ</th><th>BANG</th></tr></thead><tbody>{data?.rows.map((row) => <tr key={row.city_name + row.state}><td><span className="city-dot" />{row.city_name}</td><td className="numeric">{row.population.toLocaleString('vi-VN')}</td><td>{row.state}</td></tr>)}</tbody></table>{!data?.rows.length && <div className="table-empty">Không có thành phố phù hợp.</div>}</div>}
      <div className="pagination"><span>{data ? `${data.total} kết quả · Trang ${page}/${Math.max(1, Math.ceil(data.total / data.page_size))}` : '—'}</span><div><button className="icon-button" aria-label="Trang trước" disabled={page <= 1 || loading || !!error} onClick={() => setPage(page - 1)}><ArrowLeft size={17} /></button><button className="icon-button" aria-label="Trang sau" disabled={!data || page * data.page_size >= data.total || loading || !!error} onClick={() => setPage(page + 1)}><ArrowRight size={17} /></button></div></div>
    </div>
  </section>
}
