import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowRight, ArrowUp, Check, ChevronDown, Copy, Database, FileText, Layers3, LoaderCircle, Plus, Sparkles } from 'lucide-react'

const suggestions = [
  { icon: Database, title: 'Khám phá dữ liệu', text: 'Đơn DH1004 đã thanh toán thành công bao nhiêu tiền?', tag: 'SQL' },
  { icon: FileText, title: 'Hỏi về tài liệu', text: 'Tóm tắt những nội dung chính trong tài liệu đã tải lên.', tag: 'RAG' },
  { icon: Sparkles, title: 'Kết hợp dữ liệu', text: 'Đơn DH1002 có bị thu sai phí giao hàng theo chính sách không?', tag: 'SQL + RAG' },
]

function Answer({ message }) {
  const [copied, setCopied] = useState(false)
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])
  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      timer.current = setTimeout(() => setCopied(false), 1800)
    } catch { setCopied(false) }
  }
  return <article className={`chat-message ${message.role}`}>
    <div className={`message-avatar ${message.role === 'user' ? 'user-avatar' : ''}`}>{message.role === 'user' ? 'B' : <Layers3 size={17} />}</div>
    <div className="message-body"><div className="message-label">{message.role === 'user' ? 'Bạn' : 'Forma'}{message.duration_ms != null && <span>{(message.duration_ms / 1000).toFixed(1)}s</span>}</div>
      <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div>
      {!!message.tools?.length && <details className="tool-details"><summary><span className="tool-badge">{[...new Set(message.tools.map((tool) => tool.name))].map((name) => name === 'sql_tool' ? 'SQL' : name === 'document_tool' ? 'Tài liệu' : name).join(' + ')}</span><span>Xem kết quả tra cứu</span><ChevronDown size={14} /></summary><div className="tool-results">{message.tools.map((tool, index) => <div key={index}><strong>{tool.name}{tool.is_error ? ' · lỗi' : ''}</strong><ReactMarkdown remarkPlugins={[remarkGfm]}>{tool.content}</ReactMarkdown></div>)}</div></details>}
      {message.role === 'assistant' && <button className="copy-button" onClick={copy} aria-label="Sao chép câu trả lời">{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Đã sao chép' : 'Sao chép'}</button>}
    </div>
  </article>
}

export default function ChatView({ workspace, openSettings, openSources }) {
  const { session, busy, pending, send, ready } = workspace
  const [draft, setDraft] = useState('')
  const bottom = useRef(null)
  const input = useRef(null)
  const messages = session?.messages || []
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages.length, pending])
  useEffect(() => {
    if (input.current) { input.current.style.height = 'auto'; input.current.style.height = `${Math.min(input.current.scrollHeight, 160)}px` }
  }, [draft])
  async function submit(event) {
    event?.preventDefault()
    if (!draft.trim() || busy) return
    if (!session) { openSettings(); return }
    const question = draft
    setDraft('')
    if (!(await send(question))) setDraft(question)
    input.current?.focus()
  }
  return <section className={`chat-view ${messages.length || pending ? 'has-messages' : ''}`}>
    <div className="chat-scroll">
      {!messages.length && !pending ? <div className="welcome">
        <div className="welcome-badge"><span className="status-dot online" /> YOUR DATA, CONNECTED</div>
        <div className="welcome-symbol"><Layers3 size={31} strokeWidth={1.6} /><Sparkles size={13} className="welcome-spark" /></div>
        <h1>Dữ liệu có câu trả lời.<br /><span>Bắt đầu bằng một câu hỏi.</span></h1>
        <p>Trò chuyện với tài liệu và dữ liệu SQL của bạn.<br />Forma tìm đúng nguồn, kết nối ngữ cảnh và trả lời rõ ràng.</p>
        <div className="suggestion-grid">{suggestions.map(({ icon: Icon, title, text, tag }) => <button className="suggestion" key={title} onClick={() => { setDraft(text); input.current?.focus() }}><div><span className="suggestion-icon"><Icon size={18} /></span><span className="suggestion-tag">{tag}</span></div><strong>{title}</strong><p>{text}</p><ArrowRight size={16} className="suggestion-arrow" /></button>)}</div>
        <div className="welcome-footnote"><span className="little-line" />Một không gian. Hai nguồn dữ liệu.<span className="little-line" /></div>
      </div> : <div className="conversation">
        {messages.map((message) => <Answer key={message.id} message={message} />)}
        {pending && <><Answer message={{ role: 'user', content: pending }} /><div className="chat-message assistant"><div className="message-avatar"><Layers3 size={17} /></div><div className="message-body"><div className="message-label">Forma</div><div className="thinking"><span /><span /><span /><p>Đang tra cứu dữ liệu…</p></div></div></div></>}
        <div ref={bottom} />
      </div>}
    </div>
    <div className="composer-area"><form className="composer" onSubmit={submit}>
      <textarea ref={input} rows={1} maxLength={12000} placeholder="Hỏi bất cứ điều gì về dữ liệu của bạn…" aria-label="Câu hỏi của bạn" value={draft} disabled={!ready || !!busy} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit() } }} />
      <div className="composer-toolbar"><div><button type="button" className="attach-button" onClick={openSources} aria-label="Thêm tài liệu"><Plus size={18} /></button><span className="composer-context"><span className="status-dot" />{session ? 'Ngữ cảnh hội thoại được giữ' : 'Kết nối để bắt đầu'}</span></div><button className="send-button" type="submit" aria-label="Gửi câu hỏi" disabled={!draft.trim() || !!busy || !ready}>{busy === 'chat' ? <LoaderCircle size={18} className="spin" /> : <ArrowUp size={19} />}</button></div>
    </form><p className="composer-disclaimer">Câu trả lời dựa trên nguồn dữ liệu có sẵn. Hãy kiểm tra thông tin quan trọng.</p></div>
  </section>
}
