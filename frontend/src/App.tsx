import type { ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { ProtectedRoute } from './components/ProtectedRoute';
import { useAuth } from './context/auth-context';
import { LobbyProvider } from './context/LobbyProvider';
import { MatchProvider } from './context/MatchProvider';
import { LobbyPage } from './pages/LobbyPage';
import { LoginPage } from './pages/LoginPage';
import { MatchPage } from './pages/MatchPage';
import { RankingPage } from './pages/RankingPage';
import { RegisterPage } from './pages/RegisterPage';

/** Estado em tempo real: recomeça do zero a cada troca de usuário (logout/login). */
function Realtime({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  return (
    <LobbyProvider key={user?.id ?? 'anon'}>
      <MatchProvider key={user?.id ?? 'anon'}>{children}</MatchProvider>
    </LobbyProvider>
  );
}

export default function App() {
  return (
    <Realtime>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/lobby" element={<LobbyPage />} />
            <Route path="/match/:id" element={<MatchPage />} />
            <Route path="/ranking" element={<RankingPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/lobby" replace />} />
      </Routes>
    </Realtime>
  );
}
