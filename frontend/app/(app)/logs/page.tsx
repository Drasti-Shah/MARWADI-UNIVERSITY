"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtTime, fmtDur, dirIcon } from "@/lib/format";
import CallModal from "@/components/CallModal";

export default function LogsPage() {
  const [calls, setCalls] = useState<any[] | null>(null);
  const [sid, setSid] = useState<string | null>(null);

  function load() {
    api.get("/api/calls").then((d) => setCalls(d.calls)).catch(() => {});
  }
  useEffect(() => { load(); const id = setInterval(load, 4000); return () => clearInterval(id); }, []);

  return (
    <div className="card">
      <div className="card-head">
        <h2>Call logs</h2>
        <button className="btn btn-ghost btn-sm" onClick={load}>↻ Refresh</button>
      </div>
      <table className="table">
        <thead>
          <tr><th>Time</th><th>Dir</th><th>Name</th><th>Number</th><th>Status</th><th>Duration</th><th>Turns</th></tr>
        </thead>
        <tbody>
          {!calls ? <tr><td colSpan={7} className="muted">Loading…</td></tr>
            : !calls.length ? <tr><td colSpan={7} className="muted">No calls yet.</td></tr>
            : calls.map((c) => (
              <tr key={c.sid} className="clickable" onClick={() => setSid(c.sid)}>
                <td>{fmtTime(c.created_at)}</td>
                <td className="dir" title={c.direction}>{dirIcon(c.direction)}</td>
                <td>{c.name || <span className="muted">—</span>}</td>
                <td>{(c.direction === "outbound" ? c.to_number : c.from_number) || "—"}</td>
                <td><span className={"badge " + c.status}>{c.status || "—"}</span></td>
                <td>{fmtDur(c.duration)}</td>
                <td>{c.turns}</td>
              </tr>
            ))}
        </tbody>
      </table>
      {sid && <CallModal sid={sid} onClose={() => setSid(null)} />}
    </div>
  );
}
