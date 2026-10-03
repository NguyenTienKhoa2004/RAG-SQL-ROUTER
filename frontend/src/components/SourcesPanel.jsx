import { useRef, useState } from 'react'
import { Check, Database, FileText, LoaderCircle, LockKeyhole, Upload, X } from 'lucide-react'

export default function SourcesPanel({ workspace, onClose, openSettings }) {
  const { session, health, busy, upload } = workspace
  const fileInput = useRef(null)
  const [dragging, setDragging] = useState(false)
  const docs = session?.documents || []
  async function add(files) {
    if (!session) { openSettings(); return }
    await upload(Array.from(files))
  }
  return <aside className="sources-panel">
    <div className="sources-heading"><div><span className="eyebrow">KNOWLEDGE</span><h2>Nguồn dữ liệu</h2></div><button className="icon-button sources-close" onClick={onClose} aria-label="Đóng nguồn dữ liệu"><X size={17} /></button></div>
    <p className="sources-description">Thêm ngữ cảnh để có câu trả lời phù hợp hơn.</p>
    <div className="source-section-label">DATABASE <span>01</span></div>
    <div className="source-card"><span className="source-icon sql"><Database size={18} /></span><div><strong>City statistics</strong><small>SQLite · city_stats</small></div><span className={`status-dot ${health?.database_available ? 'online' : ''}`} title={health?.database_available ? 'Database có sẵn' : 'Database chưa sẵn sàng'} /></div>
    <div className="source-section-label documents-label">DOCUMENTS <span>{String(docs.length).padStart(2, '0')}</span></div>
    {docs.map((doc) => <div className="source-card document-card" key={doc.name}><span className="source-icon"><FileText size={18} /></span><div><strong title={doc.name}>{doc.name}</strong><small>{doc.size < 1024 ? `${doc.size} B` : `${(doc.size / 1024).toFixed(1)} KB`} · Đã xử lý</small></div><Check size={14} className="text-green" /></div>)}
    <input ref={fileInput} type="file" multiple accept=".pdf,.docx,.pptx,.txt,.md" className="visually-hidden" aria-label="Chọn tài liệu" onChange={(event) => { add(event.target.files); event.target.value = '' }} />
    <button className={`upload-zone ${dragging ? 'dragging' : ''}`} disabled={!!busy} onClick={() => session ? fileInput.current.click() : openSettings()}
      onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true) }} onDragLeave={() => setDragging(false)}
      onDrop={(event) => { event.preventDefault(); setDragging(false); if (!busy) add(event.dataTransfer.files) }}>
      <span className="upload-icon">{busy === 'upload' ? <LoaderCircle size={21} className="spin" /> : <Upload size={21} />}</span>
      <strong>{busy === 'upload' ? 'Đang xử lý tài liệu…' : 'Thả tài liệu vào đây'}</strong><span>hoặc <b>chọn từ máy tính</b></span><small>PDF, DOCX, PPTX, TXT, MD<br />Tối đa {Math.round((health?.max_upload_bytes || 20971520) / 1048576)} MB mỗi lần</small>
    </button>
    <div className="source-tip"><span className="tip-dot" /><p>{docs.length ? 'Tài liệu đã sẵn sàng. Bạn có thể hỏi trực tiếp về nội dung vừa thêm.' : 'Thêm tài liệu đầu tiên để bắt đầu hỏi về nội dung của bạn.'}</p></div>
    <div className="privacy-note"><LockKeyhole size={15} /><p>File được giữ trong session.<br />Nội dung liên quan được gửi tới LLM khi trả lời.</p></div>
  </aside>
}
