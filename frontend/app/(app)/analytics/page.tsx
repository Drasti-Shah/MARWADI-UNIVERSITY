"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fillDays, STATUS_COLORS, LEAD_COLORS } from "@/lib/format";
import { MetricCard, Bars, Donut, Funnel, HBars } from "@/components/charts";

const DIR_COLORS = { inbound: "#2563eb", outbound: "#8b5cf6", unknown: "#9ca3af" };

export default function AnalyticsPage() {
  const [a, setA] = useState<any>(null);

  useEffect(() => {
    let alive = true;
    const load = () => api.get("/api/analytics").then((d) => alive && setA(d)).catch(() => {});
    load();
    const id = setInterval(load, 6000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (!a) return <div className="muted">Loading…</div>;

  const totalCalls = Object.values(a.status_breakdown).reduce((s: number, v: any) => s + v, 0);
  const completed = a.status_breakdown.completed || 0;
  const rate = totalCalls ? Math.round((completed / totalCalls) * 100) : 0;
  const mins = Math.round(a.total_talk_time / 60);
  const leadTotal = Object.values(a.lead_status).reduce((s: number, v: any) => s + v, 0);

  return (
    <>
      <div className="metric-row">
        <MetricCard icon="📊" value={totalCalls} label="Total calls" />
        <MetricCard icon="✅" value={rate + "%"} label="Completion rate" />
        <MetricCard icon="⏱️" value={mins + "m"} label="Total talk time" />
        <MetricCard icon="👥" value={leadTotal} label="Leads" />
      </div>

      <div className="card" style={{ marginBottom: 22 }}>
        <div className="card-head"><h2>Call volume · last 14 days</h2></div>
        <div className="chart chart-tall"><Bars days={fillDays(a.calls_by_day, 14)} /></div>
      </div>

      <div className="grid-3">
        <div className="card">
          <div className="card-head"><h2>Outcomes</h2></div>
          <Donut data={a.status_breakdown} colors={STATUS_COLORS} />
        </div>
        <div className="card">
          <div className="card-head"><h2>Direction</h2></div>
          <HBars data={a.direction_breakdown} colors={DIR_COLORS} />
        </div>
        <div className="card">
          <div className="card-head"><h2>Lead funnel</h2></div>
          <Funnel counts={a.lead_status} colors={LEAD_COLORS} />
        </div>
      </div>

      <div className="card">
        <div className="card-head"><h2>Campaign performance</h2></div>
        <table className="table">
          <thead><tr><th>Campaign</th><th>Total</th><th>Done</th><th>Failed</th><th>Completion</th></tr></thead>
          <tbody>
            {a.campaign_performance.length ? a.campaign_performance.map((c: any, i: number) => {
              const pct = c.total ? Math.round((c.done / c.total) * 100) : 0;
              return <tr key={i}><td>{c.name}</td><td>{c.total}</td><td>{c.done || 0}</td><td>{c.failed || 0}</td><td>{pct}%</td></tr>;
            }) : <tr><td colSpan={5} className="muted">No campaigns yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
