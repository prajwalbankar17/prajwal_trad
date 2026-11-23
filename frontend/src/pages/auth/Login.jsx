import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, TrendingUp } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import { useAuthStore } from '../../store/auth'

export default function Login() {
  const navigate = useNavigate()
  const { setTokens, setUser, setPermissions } = useAuthStore()
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const { data } = await api.post('/auth/login', form)
      setTokens(data.access_token, data.refresh_token)
      const [me, permissions] = await Promise.all([
        api.get('/auth/me'),
        api.get('/auth/me/permissions'),
      ])
      setUser(me.data)
      setPermissions(permissions.data)
      navigate('/', { replace: true })
    } catch (err) {
      setError(errorMessage(err, 'Sign-in failed.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-lg bg-accent/15">
            <TrendingUp size={21} className="text-accent" />
          </div>
          <h1 className="text-lg font-semibold">Prajwal Trading Platform</h1>
          <p className="mt-1 text-xs text-ink-faint">
            Equity research and paper trading. Live execution is disabled.
          </p>
        </div>

        <form onSubmit={submit} className="panel p-5 space-y-4">
          <div>
            <label htmlFor="username" className="label mb-1.5 block">
              Username or email
            </label>
            <input
              id="username"
              className="input"
              autoComplete="username"
              required
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="password" className="label mb-1.5 block">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="input"
              autoComplete="current-password"
              required
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </div>

          {error && (
            <p className="rounded-md border border-loss/30 bg-loss-soft px-3 py-2 text-xs text-loss">
              {error}
            </p>
          )}

          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy && <Loader2 size={14} className="animate-spin" />}
            {busy ? 'Signing in…' : 'Sign in'}
          </button>

          <p className="text-center text-2xs text-ink-faint leading-relaxed">
            Credentials for the seeded admin account are written to
            <br />
            <code className="text-ink-muted">backend/.seed_admin_credentials.txt</code>
          </p>
        </form>
      </div>
    </div>
  )
}
