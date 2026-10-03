import { useState } from 'react'
import { Check, ChevronRight, CircleHelp, FileText, LoaderCircle, Menu, PanelRight, Plug, X } from 'lucide-react'
import Sidebar, { Brand } from './components/Sidebar'
import ChatView from './components/ChatView'
import SourcesPanel from './components/SourcesPanel'
import DatabaseView from './components/DatabaseView'
import ConnectionDialog from './components/ConnectionDialog'
import { useWorkspace } from './hooks/useWorkspace'

export default function App() {
  const workspace = useWorkspace()
  const [view, setView] = useState('chat')
  const [settings, setSettings] = useState(false)
  const [sources, setSources] = useState(true)
  const [navigation, setNavigation] = useState(false)
  const [help, setHelp] = useState(false)
  const openSettings = () => setSettings(true)
  const openSources = () => setSources(true)
  function navigate(next) { setView(next); setNavigation(false) }
  return <div className={`app-shell ${sources && view === 'chat' ? 'with-sources' : ''} ${navigation ? 'nav-open' : ''}`}>
    <Sidebar view={view} setView={navigate} workspace={workspace} openSettings={openSettings} openSources={() => { navigate('chat'); openSources() }} />
    {navigation && <button className="nav-backdrop" aria-label="Đóng menu" onClick={() => setNavigation(false)} />}
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" aria-label="Mở menu" onClick={() => setNavigation(!navigation)}><Menu size={19} /></button><span className="mobile-brand"><Brand /></span><span className="breadcrumb-home">Workspace</span><ChevronRight size={14} /><strong>{view === 'chat' ? 'Trợ lý dữ liệu' : 'Cơ sở dữ liệu'}</strong></div><div className="topbar-actions"><span className="environment-pill"><span className={`status-dot ${workspace.ready && workspace.health ? 'online' : ''}`} />Local workspace</span><button className="icon-button" aria-label="Hướng dẫn sử dụng" onClick={() => setHelp(!help)}><CircleHelp size={18} /></button>{view === 'chat' && <button className={`icon-button ${sources ? 'selected' : ''}`} onClick={() => setSources(!sources)} aria-label={sources ? 'Ẩn nguồn dữ liệu' : 'Hiện nguồn dữ liệu'}><PanelRight size={18} /></button>}</div></header>
      <div className="workspace-bar"><div><span className="workspace-title">{view === 'chat' ? 'Trò chuyện với dữ liệu' : 'Database explorer'}</span><span className="version-tag">BETA</span></div><button className={`connection-button ${workspace.session ? 'connected' : ''}`} onClick={openSettings} disabled={!workspace.ready || !!workspace.busy}>{!workspace.ready ? <LoaderCircle size={14} className="spin" /> : workspace.session ? <span className="status-dot online" /> : <Plug size={14} />}{workspace.session ? 'Đã kết nối' : 'Kết nối workspace'}</button></div>
      {workspace.error && !settings && <div className="error-banner" role="alert"><span>{workspace.error}</span><button className="icon-button" aria-label="Đóng thông báo lỗi" onClick={workspace.clearError}><X size={15} /></button></div>}
      {help && <div className="help-banner"><FileText size={18} /><p><strong>Bắt đầu với một câu hỏi.</strong> Kết nối OpenRouter, hỏi về dữ liệu thành phố hoặc upload tài liệu. Enter để gửi, Shift + Enter để xuống dòng. “Cuộc trò chuyện mới” xóa lịch sử và giữ tài liệu.</p><button className="icon-button" onClick={() => setHelp(false)} aria-label="Đóng hướng dẫn"><X size={16} /></button></div>}
      <main className="content-shell">{view === 'chat' ? <><ChatView workspace={workspace} openSettings={openSettings} openSources={openSources} />{sources && <SourcesPanel workspace={workspace} onClose={() => setSources(false)} openSettings={openSettings} />}</> : <DatabaseView />}</main>
    </div>
    {workspace.notice && <div className="toast" role="status"><Check size={16} />{workspace.notice}</div>}
    <ConnectionDialog open={settings} onClose={() => setSettings(false)} workspace={workspace} />
  </div>
}
