import { createContext, useContext, useState, ReactNode } from "react";
import { api, setToken } from "./api";
import { LoginResponse, Role } from "./types";

interface AuthState {
  token: string | null;
  role: Role | null;
  fullName: string | null;
  userId: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function loadInitial() {
  return {
    token: localStorage.getItem("token"),
    role: (localStorage.getItem("role") as Role | null) ?? null,
    fullName: localStorage.getItem("fullName"),
    userId: localStorage.getItem("userId"),
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(loadInitial());

  async function login(email: string, password: string) {
    const res = await api.post<LoginResponse>("/auth/login", { email, password });
    setToken(res.access_token);
    localStorage.setItem("role", res.role);
    localStorage.setItem("fullName", res.full_name);
    localStorage.setItem("userId", res.user_id);
    setState({ token: res.access_token, role: res.role, fullName: res.full_name, userId: res.user_id });
  }

  function logout() {
    setToken(null);
    localStorage.removeItem("role");
    localStorage.removeItem("fullName");
    localStorage.removeItem("userId");
    setState({ token: null, role: null, fullName: null, userId: null });
  }

  return <AuthContext.Provider value={{ ...state, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
