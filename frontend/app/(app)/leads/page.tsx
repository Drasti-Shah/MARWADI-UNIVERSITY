"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { LEAD_COLORS, colorFor } from "@/lib/format";

export default function LeadsPage() {
  const [data, setData] = useState<any>(null);
  const [filter, setFilter] = useState("");
  const [form, setForm] = useState({ name: "", phone: "", qualification: "", interest: "", status: "new", notes: "" });
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const statuses: string[] = data?.statuses || ["new", "contacted", "interested", "enrolled", "lost"];

  function load() {
    api.get("/api/leads" + (filter ? `?status=${filter}` : "")).then(setData).catch(() => {});
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter]);
  useEffect(() => { const id = setInterval(load, 6000); return () => clearInterval(id); /* eslint-disable-next-line */ }, [filter]);

  async function addLead() {
    if (!form.phone.trim()) { setResult({ ok: false, msg: "Phone is required." }); return; }
    try {
      await api.post("/api/leads", form);
      setResult({ ok: true, msg: "✅ Lead added." });
      setForm({ name: "", phone: "", qualification: "", interest: "", status: "new", notes: "" });
      load();
    } catch (e: any) {
      setResult({ ok: false, msg: `❌ ${e.message}` });
    }
  }

  async function changeStatus(id: number, status: string) {
    await api.patch(`/api/leads/${id}`, { status });
    load();
  }
  async function remove(id: number) {
    if (!confirm("Delete this lead?")) return;
    await api.del(`/api/leads/${id}`);
    load();
  }

  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="grid-2">
      <div className="card">
        <h2>Add lead</h2>
        <label className="lbl">Name</label>
        <input className="input" value={form.name} onChange={set("name")} placeholder="Student name" />
        <label className="lbl">Phone</label>
        <input className="input" value={form.phone} onChange={set("phone")} placeholder="9724556935" />
        <label className="lbl">Qualification</label>
        <input className="input" value={form.qualification} onChange={set("qualification")} placeholder="12th Science" />
        <label className="lbl">Interest</label>
        <input className="input" value={form.interest} onChange={set("interest")} placeholder="B.Tech CSE" />
        <label className="lbl">Status</label>
        <select className="input" value={form.status} onChange={set("status")}>
          {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <label className="lbl">Notes</label>
        <textarea className="input" rows={2} value={form.notes} onChange={set("notes")} />
        <button className="btn btn-primary" onClick={addLead}>Add lead</button>
        {result && <div className={"result " + (result.ok ? "ok" : "err")}>{result.msg}</div>}
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Leads</h2>
          <select className="input filter-select" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All statuses</option>
            {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <table className="table">
          <thead><tr><th>Name</th><th>Phone</th><th>Qualification</th><th>Status</th><th>Source</th><th></th></tr></thead>
          <tbody>
            {!data ? <tr><td colSpan={6} className="muted">Loading…</td></tr>
              : !data.leads.length ? <tr><td colSpan={6} className="muted">No leads yet. Calls auto-create leads, or add one manually.</td></tr>
              : data.leads.map((l: any) => (
                <tr key={l.id}>
                  <td>{l.name || <span className="muted">—</span>}</td>
                  <td>{l.phone}</td>
                  <td>{l.qualification || <span className="muted">—</span>}</td>
                  <td>
                    <select className="status-select" value={l.status}
                            style={{ color: colorFor(l.status, LEAD_COLORS) }}
                            onChange={(e) => changeStatus(l.id, e.target.value)}>
                      {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td><span className="muted">{l.source}</span></td>
                  <td><button className="icon-btn" title="Delete" onClick={() => remove(l.id)}>🗑</button></td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
