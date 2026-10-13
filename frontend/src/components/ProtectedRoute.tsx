import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/auth-context'

export function ProtectedRoute() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <p className="screen-note">Entrando…</p>
  if (status === 'anon') return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}
