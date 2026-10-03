import { useEffect, useRef, useState } from 'react'
import { ArrowRight, KeyRound, LoaderCircle, X } from 'lucide-react'

export default function ConnectionDialog({ open, onClose, workspace }) {
  const [key, setKey] = useState('')
  const dialog = useRef(null)
  const { session, health, busy, connect, disconnect, error, clearError } = workspace
  useEffect(() => {
    if (open && !dialog.current.open) dialog.current.showModal()
    if (!open && dialog.current.open) dialog.current.close()
    if (!open) setKey('')
  }, [open])

  async function submit(event) {
    event.preventDefault()
    if (await connect(key)) { setKey(''); onClose() }
  }

  return <dialog ref={dialog} className="connection-dialog" onCancel={onClose} onClick={(event) => { if (event.target === dialog.current && !busy) onClose() }}>
    <button className="icon-button dialog-close" aria-label="Đóng cài đặt" onClick={onClose} disabled={!!busy}><X size={19} /></button>
    <span className="dialog-symbol"><KeyRound size={24} /></span>
    <h2>{session ? 'Workspace của bạn' : 'Kết nối workspace'}</h2>
    <p>{session ? 'Bạn đã sẵn sàng trò chuyện với dữ liệu.' : 'Thêm OpenRouter API key để bắt đầu trò chuyện với tài liệu và dữ liệu SQL.'}</p>
    {session ? <>
      <div className="connection-detail"><span>Model</span><strong>{session.model}</strong></div>
      <div className="connection-detail"><span>Trạng thái</span><strong className="text-green">Đã kết nối</strong></div>
      <button className="button secondary full-width" disabled={!!busy} onClick={async () => { if (await disconnect()) onClose() }}>{busy === 'disconnect' ? 'Đang ngắt kết nối…' : 'Ngắt kết nối'}</button>
    </> : <form onSubmit={submit}>
      <label htmlFor="api-key">OpenRouter API key</label>
      <input id="api-key" type="password" placeholder={health?.server_key_configured ? 'Để trống để dùng key của server' : 'sk-or-v1-…'} autoComplete="off" value={key} onChange={(event) => { setKey(event.target.value); clearError() }} autoFocus />
      <small className="field-hint">Key chỉ dùng cho session hiện tại, không lưu vào trình duyệt.</small>
      {error && <div className="dialog-error" role="alert">{error}</div>}
      <button className="button primary full-width" disabled={!!busy || (!key.trim() && !health?.server_key_configured)}>{busy === 'connect' ? <LoaderCircle size={17} className="spin" /> : <ArrowRight size={17} />} {busy === 'connect' ? 'Đang kết nối…' : 'Kết nối workspace'}</button>
      <a className="key-link" href="https://openrouter.ai/keys" target="_blank" rel="noreferrer">Lấy API key trên OpenRouter ↗</a>
    </form>}
  </dialog>
}
