import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import NewEncounter from "./pages/NewEncounter";
import EncounterEditor from "./pages/EncounterEditor";
import AdminDashboard from "./pages/AdminDashboard";

function TopBar() {
  const { fullName, role, logout } = useAuth();
  return (
    <div className="topbar">
      <div className="topbar-brand">
        <span className="mark">KC</span>
        Kyron Clinical Scribe
      </div>
      <div className="topbar-user">
        <span>
          {fullName} <span className="muted">({role})</span>
        </span>
        <button className="ghost" onClick={logout}>
          Sign out
        </button>
      </div>
    </div>
  );
}

function RequireAuth({ children, roles }: { children: JSX.Element; roles?: ("provider" | "admin")[] }) {
  const { token, role: currentRole } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  if (roles && currentRole && !roles.includes(currentRole)) return <Navigate to="/" replace />;
  return (
    <div className="app-shell">
      <TopBar />
      {children}
    </div>
  );
}

export default function App() {
  const { role } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            {role === "admin" ? <AdminDashboard /> : <Dashboard />}
          </RequireAuth>
        }
      />
      <Route
        path="/encounters/new"
        element={
          <RequireAuth roles={["provider"]}>
            <NewEncounter />
          </RequireAuth>
        }
      />
      <Route
        path="/encounters/:id"
        element={
          <RequireAuth roles={["provider", "admin"]}>
            <EncounterEditor />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
