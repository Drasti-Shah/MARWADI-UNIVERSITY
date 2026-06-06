"use client";

import { colorFor, DayPoint } from "@/lib/format";

export function MetricCard({ icon, value, label }: { icon: string; value: React.ReactNode; label: string }) {
  return (
    <div className="metric">
      <div className="m-top"><div className="m-icon">{icon}</div></div>
      <div className="m-val">{value}</div>
      <div className="m-label">{label}</div>
    </div>
  );
}

export function Bars({ days }: { days: DayPoint[] }) {
  const max = Math.max(1, ...days.map((d) => d.total));
  return (
    <>
      {days.map((d) => {
        const h = Math.round((d.total / max) * 100);
        const ch = d.total ? Math.round((d.completed / d.total) * h) : 0;
        return (
          <div className="bar-col" key={d.day} title={`${d.day}: ${d.total} calls, ${d.completed} completed`}>
            <div className="bar-cap">{d.total || ""}</div>
            <div className="bar-stack">
              <div className="bar-fill" style={{ height: `${h}%` }}>
                <div className="bar-fill" style={{ height: `${ch}%`, width: "100%", margin: 0, background: "#34d399" }} />
              </div>
            </div>
            <div className="bar-x">{d.day.slice(5)}</div>
          </div>
        );
      })}
    </>
  );
}

export function Donut({ data, colors }: { data: Record<string, number>; colors: Record<string, string> }) {
  const entries = Object.entries(data).filter(([, v]) => v > 0);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  if (!total) {
    return (
      <div className="donut-wrap">
        <div className="donut" style={{ background: "#eceefb" }}>
          <div className="donut-center" style={{ fontSize: 13, color: "var(--muted)" }}>No data</div>
        </div>
      </div>
    );
  }
  let acc = 0;
  const segs = entries.map(([k, v]) => {
    const start = (acc / total) * 100;
    acc += v;
    const end = (acc / total) * 100;
    return `${colorFor(k, colors)} ${start}% ${end}%`;
  });
  return (
    <div className="donut-wrap">
      <div className="donut" style={{ background: `conic-gradient(${segs.join(",")})` }}>
        <div className="donut-center">{total}</div>
      </div>
      <div className="legend">
        {entries.map(([k, v]) => (
          <div className="li" key={k}>
            <span className="sw" style={{ background: colorFor(k, colors) }} />
            <span style={{ textTransform: "capitalize" }}>{k}</span>
            <span className="lv">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Funnel({ counts, colors }: { counts: Record<string, number>; colors: Record<string, string> }) {
  const max = Math.max(1, ...Object.values(counts));
  return (
    <div className="funnel">
      {Object.entries(counts).map(([k, v]) => {
        const w = Math.round((v / max) * 100);
        return (
          <div className="fstep" key={k}>
            <span className="flabel">{k}</span>
            <div className="fbar" style={{ width: `${Math.max(w, 8)}%`, background: colorFor(k, colors) }}>{v}</div>
          </div>
        );
      })}
    </div>
  );
}

export function HBars({ data, colors }: { data: Record<string, number>; colors: Record<string, string> }) {
  const total = Object.values(data).reduce((s, v) => s + v, 0) || 1;
  return (
    <div className="hbars">
      {Object.entries(data).map(([k, v]) => {
        const pct = Math.round((v / total) * 100);
        return (
          <div className="hbar" key={k}>
            <div className="hbar-top"><span style={{ textTransform: "capitalize" }}>{k}</span><span>{v}</span></div>
            <div className="track"><div style={{ width: `${pct}%`, background: colorFor(k, colors) }} /></div>
          </div>
        );
      })}
    </div>
  );
}
