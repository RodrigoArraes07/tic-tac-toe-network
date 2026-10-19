import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/auth-context';
import { AuthLayout } from './AuthLayout';

interface LoginLocationState {
  registered?: boolean;
  username?: string;
}

export function LoginPage() {
  const { status, login } = useAuth();
  const location = useLocation();
  const hint = (location.state ?? {}) as LoginLocationState;

  const [username, setUsername] = useState(hint.username ?? '');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === 'authed') return <Navigate to="/lobby" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (submitting) return;
    if (!username.trim() || !password) {
      setError('Informe usuário e senha.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Entrar">
      {hint.registered && (
        <p className="notice" role="status">
          Conta criada. Entre com sua senha.
        </p>
      )}
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
            autoFocus={!hint.username}
          />
        </div>
        <div className="field">
          <label htmlFor="password">Senha</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            autoFocus={Boolean(hint.username)}
          />
        </div>
        {error && (
          <p className="form__error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="btn" disabled={submitting}>
          {submitting ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
      <p className="form__alt">
        Ainda não tem conta? <Link to="/register">Criar conta</Link>
      </p>
    </AuthLayout>
  );
}
