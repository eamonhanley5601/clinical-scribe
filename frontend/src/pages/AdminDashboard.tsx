import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { Encounter, Provider, Template } from "../types";

type Tab = "encounters" | "providers" | "templates";

export default function AdminDashboard() {
  const [tab, setTab] = useState<Tab>("encounters");

  return (
    <div className="page">
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: "0 0 20px" }}>Admin</h1>
      <div className="tabs">
        <button className={tab === "encounters" ? "active" : ""} onClick={() => setTab("encounters")}>
          All encounters
        </button>
        <button className={tab === "providers" ? "active" : ""} onClick={() => setTab("providers")}>
          Providers
        </button>
        <button className={tab === "templates" ? "active" : ""} onClick={() => setTab("templates")}>
          Note templates
        </button>
      </div>
      {tab === "encounters" && <EncountersTab />}
      {tab === "providers" && <ProvidersTab />}
      {tab === "templates" && <TemplatesTab />}
    </div>
  );
}

function EncountersTab() {
  const navigate = useNavigate();
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [providerId, setProviderId] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  useEffect(() => {
    api.get<Provider[]>("/admin/providers").then(setProviders);
  }, []);

  // Re-fetches automatically whenever a filter changes -- no explicit "Filter" button needed.
  useEffect(() => {
    const params = new URLSearchParams();
    if (providerId) params.set("provider_id", providerId);
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    api.get<Encounter[]>(`/admin/encounters?${params.toString()}`).then(setEncounters);
  }, [providerId, startDate, endDate]);

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">All encounters</span>
      </div>
      <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
        <div style={{ flex: 1 }}>
          <label>Provider</label>
          <select value={providerId} onChange={(e) => setProviderId(e.target.value)}>
            <option value="">All providers</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name}
              </option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label>From</label>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </div>
        <div style={{ flex: 1 }}>
          <label>To</label>
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Patient</th>
            <th>Provider</th>
            <th>Status</th>
            <th>Versions</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {encounters.map((e) => (
            <tr key={e.id} className="clickable-row" onClick={() => navigate(`/encounters/${e.id}`)}>
              <td>
                {e.patient.first_name} {e.patient.last_name}
              </td>
              <td>{e.provider_name}</td>
              <td>{e.status}</td>
              <td>{e.latest_version}</td>
              <td>{new Date(e.updated_at).toLocaleString()}</td>
            </tr>
          ))}
          {encounters.length === 0 && (
            <tr>
              <td colSpan={5} className="muted">
                No encounters match these filters.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ProvidersTab() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setProviders(await api.get<Provider[]>("/admin/providers"));
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/admin/providers", { email, full_name: fullName, password });
      setEmail("");
      setFullName("");
      setPassword("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create provider");
    }
  }

  async function toggle(p: Provider) {
    const action = p.is_active ? "deactivate" : "reactivate";
    await api.post(`/admin/providers/${p.id}/${action}`);
    load();
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: 16, alignItems: "start" }}>
      <form className="card" onSubmit={handleCreate}>
        <div className="card-header">
          <span className="card-title">Add provider</span>
        </div>
        {error && <div className="error-banner">{error}</div>}
        <div className="field">
          <label>Full name</label>
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
        </div>
        <div className="field">
          <label>Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="field">
          <label>Temporary password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <button className="primary" type="submit" style={{ width: "100%" }}>
          Add provider
        </button>
      </form>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Provider roster</span>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.id}>
                <td>{p.full_name}</td>
                <td>{p.email}</td>
                <td>{p.is_active ? "Active" : "Deactivated"}</td>
                <td>
                  <button className={p.is_active ? "danger" : "primary"} onClick={() => toggle(p)}>
                    {p.is_active ? "Deactivate" : "Reactivate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TemplatesTab() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [editing, setEditing] = useState<Template | null>(null);
  const [name, setName] = useState("");
  const [instructions, setInstructions] = useState("");

  async function load() {
    setTemplates(await api.get<Template[]>("/admin/templates"));
  }

  useEffect(() => {
    load();
  }, []);

  function edit(t: Template | null) {
    setEditing(t);
    setName(t?.name ?? "");
    setInstructions(t?.prompt_instructions ?? "");
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    const body = { name, prompt_instructions: instructions };
    if (editing) {
      await api.patch(`/admin/templates/${editing.id}`, body);
    } else {
      await api.post("/admin/templates", body);
    }
    edit(null);
    load();
  }

  async function toggleActive(t: Template) {
    await api.patch(`/admin/templates/${t.id}`, { is_active: !t.is_active });
    load();
  }

  async function remove(t: Template) {
    await api.delete(`/admin/templates/${t.id}`);
    load();
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: 16, alignItems: "start" }}>
      <form className="card" onSubmit={handleSave}>
        <div className="card-header">
          <span className="card-title">{editing ? "Edit template" : "New template"}</span>
        </div>
        <div className="field">
          <label>Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="field">
          <label>Prompt instructions</label>
          <textarea style={{ minHeight: 160 }} value={instructions} onChange={(e) => setInstructions(e.target.value)} required />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="primary" type="submit" style={{ flex: 1 }}>
            {editing ? "Save changes" : "Create template"}
          </button>
          {editing && (
            <button type="button" className="ghost" onClick={() => edit(null)}>
              Cancel
            </button>
          )}
        </div>
        <p className="muted" style={{ marginTop: 10 }}>
          Changes take effect on a provider's very next note generation — no refresh needed on their end.
        </p>
      </form>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Templates</span>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {templates.map((t) => (
              <tr key={t.id}>
                <td>{t.name}</td>
                <td>{t.encounter_type}</td>
                <td>{t.is_active ? "Active" : "Inactive"}</td>
                <td style={{ display: "flex", gap: 6 }}>
                  <button className="ghost" onClick={() => edit(t)}>
                    Edit
                  </button>
                  <button className="ghost" onClick={() => toggleActive(t)}>
                    {t.is_active ? "Deactivate" : "Activate"}
                  </button>
                  <button className="danger" onClick={() => remove(t)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
