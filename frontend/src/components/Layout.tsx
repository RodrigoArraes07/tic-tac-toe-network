import { useEffect } from 'react';
import { Link, NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../context/auth-context';
import { useToast } from '../context/toast-context';
import { gameSocket } from '../socket';
import { ConnectionBadge } from './ConnectionBadge';
import { InviteDialog } from './InviteDialog';

export function Layout() {
  const { user, socketStatus, logout, resumeSocket } = useAuth();
  const toast = useToast();

  // Todo ERROR do servidor vira um aviso curto (seção 13.4).
  useEffect(
    () =>
      gameSocket.subscribe('ERROR', (m) => {
        if (m.payload.code === 'STALE_STATE') return; // o MatchProvider ressincroniza em silêncio
        toast.push(m.payload.message, 'error');
      }),
    [toast],
  );

  return (
    <>
      <header className="topbar">
        <Link to="/lobby" className="brand">
          Jogo da velha
        </Link>
        <nav className="topbar__nav" aria-label="Principal">
          <NavLink to="/lobby">Lobby</NavLink>
          <NavLink to="/ranking">Ranking</NavLink>
        </nav>
        <div className="topbar__user">
          <ConnectionBadge status={socketStatus} />
          <span className="topbar__name">{user?.username}</span>
          <button type="button" className="btn btn--ghost btn--small" onClick={logout}>
            Sair
          </button>
        </div>
      </header>

      {socketStatus === 'replaced' && (
        <div className="banner banner--warn" role="alert">
          <span>Sua conta foi aberta em outra aba, então esta parou de receber atualizações.</span>
          <button type="button" className="btn btn--small" onClick={resumeSocket}>
            Usar esta aba
          </button>
        </div>
      )}

      <main className="page">
        <Outlet />
      </main>
      <InviteDialog />
    </>
  );
}
