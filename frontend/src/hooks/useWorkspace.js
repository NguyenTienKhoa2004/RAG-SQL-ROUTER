import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

const STORAGE_KEY = 'forma-session'

export function useWorkspace() {
  const [session, setSession] = useState(null)
  const [health, setHealth] = useState(null)
  const [ready, setReady] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState('')
  const [notice, setNotice] = useState('')
  const operation = useRef(false)

  useEffect(() => {
    let active = true
    async function restore() {
      try {
        const status = await api.health()
        if (active) setHealth(status)
        const id = sessionStorage.getItem(STORAGE_KEY)
        if (id) {
          try {
            const restored = await api.session(id)
            if (active) setSession(restored)
          } catch (err) {
            if (err.status === 404) sessionStorage.removeItem(STORAGE_KEY)
            else throw err
          }
        }
      } catch (err) {
        if (active) setError(err.message)
      } finally { if (active) setReady(true) }
    }
    restore()
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(''), 4500)
    return () => clearTimeout(timer)
  }, [notice])

  async function perform(kind, action) {
    if (operation.current) return false
    operation.current = true
    setBusy(kind); setError('')
    try { await action(); return true }
    catch (err) {
      setError(err.message)
      if (err.status === 404) {
        setSession(null)
        sessionStorage.removeItem(STORAGE_KEY)
      }
      return false
    } finally { operation.current = false; setBusy('') }
  }

  const connect = (key) => perform('connect', async () => {
    const next = await api.connect(key)
    sessionStorage.setItem(STORAGE_KEY, next.id)
    setSession(next)
    setNotice('Workspace đã sẵn sàng')
  })

  const send = (question) => {
    const text = question.trim()
    if (!session || !text) return Promise.resolve(false)
    return perform('chat', async () => {
      setPending(text)
      try {
        const answer = await api.chat(session.id, text)
        setSession((current) => ({ ...current, messages: [...current.messages,
          { id: crypto.randomUUID(), role: 'user', content: text, tools: [] }, answer,
        ] }))
      } finally { setPending('') }
    })
  }

  const upload = (files) => {
    if (!session) { setError('Kết nối workspace trước khi thêm tài liệu.'); return Promise.resolve(false) }
    if (!files.length) return Promise.resolve(false)
    const total = files.reduce((sum, file) => sum + file.size, 0)
    if (health && total > health.max_upload_bytes) {
      setError(`Tổng dung lượng tối đa ${Math.round(health.max_upload_bytes / 1048576)} MB mỗi lần upload.`)
      return Promise.resolve(false)
    }
    return perform('upload', async () => {
      setSession(await api.upload(session.id, files))
      setNotice('Tài liệu đã được xử lý và sẵn sàng tra cứu')
    })
  }

  const reset = () => session && perform('reset', async () => {
    setSession(await api.reset(session.id))
    setNotice('Đã bắt đầu cuộc trò chuyện mới')
  })

  const disconnect = () => session && perform('disconnect', async () => {
    await api.disconnect(session.id)
    sessionStorage.removeItem(STORAGE_KEY)
    setSession(null)
  })

  return { session, health, ready, busy, error, pending, notice,
    connect, send, upload, reset, disconnect, clearError: () => setError('') }
}
