import { ArrowUpRight, Database, FileText, Layers3, MessageSquare, Plus, Settings2 } from 'lucide-react'

export function Brand() {
  return <div className="brand"><span className="brand-mark"><Layers3 size={21} strokeWidth={2} /></span><span>forma<span className="brand-dot">.</span></span></div>
}

export default function Sidebar({ view, setView, workspace, openSettings, openSources }) {
  const { session, busy, reset } = workspace
  return <aside className="sidebar">
    <Brand />
    <div className="workspace-label"><span className="workspace-avatar">P</span><div>Personal workspace<small>RAG + SQL</small></div><span className="workspace-badge">LOCAL</span></div>
    <button className="new-chat" onClick={() => { setView('chat'); reset() }} disabled={!session || !!busy}><Plus size={17} />Cuộc trò chuyện mới</button>
    <div className="nav-caption">WORKSPACE</div>
    <nav aria-label="Điều hướng chính">
      <button className={`nav-item ${view === 'chat' ? 'active' : ''}`} onClick={() => setView('chat')}><MessageSquare size={18} />Trợ lý dữ liệu<span className="nav-dot" /></button>
      <button className={`nav-item ${view === 'database' ? 'active' : ''}`} onClick={() => setView('database')}><Database size={18} />Cơ sở dữ liệu<ArrowUpRight size={14} className="nav-end" /></button>
      <button className="nav-item" onClick={openSources}><FileText size={18} />Tài liệu<span className="nav-count">{session?.documents.length || 0}</span></button>
    </nav>
    <div className="sidebar-note"><div className="note-icon"><Layers3 size={17} /></div><strong>Dữ liệu của bạn. Câu trả lời rõ ràng.</strong><p>Kết nối tài liệu và SQL trong cùng một cuộc trò chuyện.</p><span>Built with LlamaIndex <ArrowUpRight size={12} /></span></div>
    <button className="sidebar-profile" onClick={openSettings}><span className="profile-avatar">AS</span><div>Workspace settings<small>{session ? 'Đã kết nối OpenRouter' : 'Chưa kết nối'}</small></div><Settings2 size={17} /></button>
  </aside>
}
