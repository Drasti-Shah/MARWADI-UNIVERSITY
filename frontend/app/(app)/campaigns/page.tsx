"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { colorFor, LEAD_COLORS } from "@/lib/format";

// Extract phone-like tokens from an uploaded CSV (any column/header layout).
function extractNumbers(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  const re = /\+?\d[\d\s\-()]{7,}\d/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const num = m[0].replace(/[\s\-()]/g, "");
    if (!seen.has(num)) { seen.add(num); out.push(num); }
  }
  return out;
}

export default function CampaignsPage() {
  const [name, setName] = useState("");
  const [numbers, setNumbers] = useState("");
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [csvHint, setCsvHint] = useState<{ msg: string; ok: boolean } | null>(null);

  async function load() {
    try {
      const { campaigns } = await api.get("/api/campaigns");
      const detailed = await Promise.all(campaigns.map((c: any) => api.get(`/api/campaigns/${c.id}`)));
      setCampaigns(detailed);
    } catch {}
  }
  useEffect(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id); }, []);

  function onCsv(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const nums = extractNumbers(String(reader.result));
      if (!nums.length) { setCsvHint({ msg: "No phone numbers found in that file.", ok: false }); return; }
      const existing = numbers.split("\n").map((s) => s.trim()).filter(Boolean);
      setNumbers(Array.from(new Set([...existing, ...nums])).join("\n"));
      setCsvHint({ msg: `✓ ${nums.length} number(s) loaded from ${file.name}`, ok: true });
    };
    reader.readAsText(file);
    e.target.value = "";
  }

  async function create() {
    const nums = numbers.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!name.trim() || !nums.length) { setResult({ ok: false, msg: "Name and at least one number are required." }); return; }
    try {
      await api.post("/api/campaigns", { name: name.trim(), numbers: nums });
      setResult({ ok: true, msg: `✅ Campaign created with ${nums.length} number(s).` });
      setName(""); setNumbers(""); setCsvHint(null);
      load();
    } catch (e: any) {
      setResult({ ok: false, msg: `❌ ${e.message}` });
    }
  }

  async function start(id: number) {
    try { await api.post(`/api/campaigns/${id}/start`); } catch (e: any) { alert(e.message); }
    load();
  }

  return (
    <div className="grid-2">
      <div className="card">
        <h2>New campaign</h2>
        <label className="lbl">Name</label>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. B.Tech outreach – June" />
        <label className="lbl">Numbers <span className="muted">(one per line)</span></label>
        <div className="csv-row">
          <label className="csv-label">📄 Upload CSV
            <input type="file" accept=".csv,text/csv" onChange={onCsv} />
          </label>
          <span className="csv-hint" style={csvHint ? { color: csvHint.ok ? "var(--green)" : "var(--red)" } : undefined}>
            {csvHint ? csvHint.msg : "or paste below"}
          </span>
        </div>
        <textarea className="input" rows={6} value={numbers} onChange={(e) => setNumbers(e.target.value)}
                  placeholder={"9724556935\n+919876543210"} />
        <button className="btn btn-primary" onClick={create}>Create campaign</button>
        {result && <div className={"result " + (result.ok ? "ok" : "err")}>{result.msg}</div>}
      </div>

      <div className="card">
        <h2>Campaigns</h2>
        <div className="camp-list">
          {!campaigns.length ? <div className="muted">No campaigns yet.</div>
            : campaigns.map((c) => {
              const total = c.numbers.length;
              const done = c.numbers.filter((n: any) => ["done", "failed"].includes(n.status)).length;
              const pct = total ? Math.round((done / total) * 100) : 0;
              return (
                <div className="camp" key={c.id}>
                  <div className="camp-top">
                    <span className="camp-name">{c.name}</span>
                    <span className={"badge " + c.status}>{c.status}</span>
                  </div>
                  <div className="progress"><div style={{ width: `${pct}%` }} /></div>
                  <div className="camp-meta">
                    <span>{done}/{total} done</span>
                    {c.status !== "running"
                      ? <button className="btn btn-primary btn-sm" onClick={() => start(c.id)}>▶ Start</button>
                      : <span className="muted">running…</span>}
                  </div>
                  <div className="camp-numbers">
                    {c.numbers.map((n: any) => (
                      <span className="num-chip" key={n.id}>
                        <span className={"badge " + n.status}>{n.status}</span>{n.number}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
        </div>
      </div>
    </div>
  );
}
