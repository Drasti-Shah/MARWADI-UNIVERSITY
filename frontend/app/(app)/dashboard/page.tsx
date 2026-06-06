"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtTime, fmtDur, dirIcon, fillDays, STATUS_COLORS, LEAD_COLORS } from "@/lib/format";
import { MetricCard, Bars, Donut, Funnel } from "@/components/charts";
import CallModal from "@/components/CallModal";

export default function DashboardPage() {
  const [o, setO] = useState<any>(null);
  const [sid, setSid] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => api.get("/api/overview").then((d) => alive && setO(d)).catch(() => {});
    load();
    const id = setInterval(load, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (!o) return <div className="muted">Loading…</div>;

  return (
    <>
      <div className="metric-row">
        <MetricCard icon="📞" value={o.total_calls} label="Total calls" />
        <MetricCard icon="📅" value={o.calls_today} label="Calls today" />
        <MetricCard icon="👥" value={o.leads} label="Leads" />
        <MetricCard icon="⏱️" value={o.avg_duration + "s"} label="Avg duration" />
      </div>

      <div className="grid-2-eq">
        <div className="card">
          <div className="card-head"><h2>Calls · last 7 days</h2></div>
          <div className="chart"><Bars days={fillDays(o.calls_by_day, 7)} /></div>
        </div>
        <div className="card">
          <div className="card-head"><h2>Call outcomes</h2></div>
          <Donut data={o.status_breakdown} colors={STATUS_COLORS} />
        </div>
      </div>

      <div className="grid-2-eq">
        <div className="card">
          <div className="card-head"><h2>Recent calls</h2></div>
          <table className="table">
            <tbody>
              {o.recent_calls.length ? o.recent_calls.map((c: any) => (
                <tr key={c.sid} className="clickable" onClick={() => setSid(c.sid)}>
                  <td className="dir">{dirIcon(c.direction)}</td>
                  <td>{(c.direction === "outbound" ? c.to_number : c.from_number) || "—"}</td>
                  <td><span className={"badge " + c.status}>{c.status || "—"}</span></td>
                  <td>{fmtDur(c.duration)}</td>
                  <td className="muted">{fmtTime(c.created_at)}</td>
                </tr>
              )) : <tr><td className="muted">No calls yet.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="card">
          <div className="card-head"><h2>Lead funnel</h2></div>
          <Funnel counts={o.lead_status} colors={LEAD_COLORS} />
        </div>
      </div>

      {sid && <CallModal sid={sid} onClose={() => setSid(null)} />}
    </>
  );
}
