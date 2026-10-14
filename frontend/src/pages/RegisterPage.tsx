import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth-context'
import { validatePassword, validateUsername } from '../validation'
import { AuthLayout } from './AuthLayout'

export function RegisterPage() {
  const { status, register } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<{ username?: string; password?: string; confirm?: string; form?: string }>({})
  const [submitting, setSubmitting] = useState(false)

  if (status === 'authed') return <Navigate to="/lobby" replace />

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (submitting) return
    const name = username.trim()
    const next = {
      username: validateUsername(name) ?? undefined,
      password: validatePassword(password) ?? undefined,
      confirm: confirm !== password ? 'As senhas não são iguais.' : undefined,
    }
    setErrors(next)
    if (next.username || next.password || next.confirm) return

    setSubmitting(true)
    try {
      await register(name, password)
      navigate('/login', { replace: true, state: { registered: true, username: name } })
    } catch (err) {
      setErrors({ form: (err as Error).message })
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout title="Criar conta">
      <form onSubmit={onSubmit} className="form" noValidate>
        <div className="field">
          <label htmlFor="username">Usuário</label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            aria-invalid={Boolean(errors.username)}
            aria-describedby="username-help"
            autoFocus
          />
          <p id="username-help" className={errors.username ? 'field__help field__help--error' : 'field__help'}>
            {errors.username ?? '3 a 20 caracteres: letras, números e _.'}
          </p>
        </div>
        <div className="field">
          <label htmlFor="password">Senha</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            aria-invalid={Boolean(errors.password)}
            aria-describedby="password-help"
          />
          <p id="password-help" className={errors.password ? 'field__help field__help--error' : 'field__help'}>
            {errors.password ?? 'De 8 a 72 caracteres.'}
          </p>
        </div>
        <div className="field">
          <label htmlFor="confirm">Repita a senha</label>
          <input
            id="confirm"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            aria-invalid={Boolean(errors.confirm)}
            aria-describedby="confirm-help"
          />
          <p id="confirm-help" className="field__help field__help--error">
            {errors.confirm}
          </p>
        </div>
        {errors.form && (
          <p className="form__error" role="alert">
            {errors.form}
          </p>
        )}
        <button type="submit" className="btn" disabled={submitting}>
          {submitting ? 'Criando…' : 'Criar conta'}
        </button>
      </form>
      <p className="form__alt">
        Já tem conta? <Link to="/login">Entrar</Link>
      </p>
    </AuthLayout>
  )
}
