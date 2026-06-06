"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { api } from "@/lib/api";

const TITLES: Record<string, string> = {
  "/dashboard": "Dashboard", "/dialer": "Dialer", "/leads": "Leads",
  "/campaigns": "Campaigns", "/analytics": "Analytics", "/logs": "Call Logs",
};

type Stats = {
  total_calls: number; completed_calls: number; avg_duration: number;
  leads: number; campaigns: number;
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [stats, setStats] = useState<Stats | null>(null);
  const [connected, setConnected] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const s = await api.get("/api/stats");
        if (!alive) return;
        setStats(s);
        setConnected(true);
        setReady(true);
      } catch {
        // api wrapper redirects to /login on 401
        if (alive) setConnected(false);
      }
    }
    load();
    const id = setInterval(load, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <div className="shell">
      <Sidebar connected={connected} />
      <main className="content">
        <header className="topbar">
          <h1>{TITLES[pathname] || "Console"}</h1>
          <div className="stats">
            <div className="stat"><div className="stat-num">{stats?.total_calls ?? "–"}</div><div className="stat-label">Total calls</div></div>
            <div className="stat"><div className="stat-num">{stats?.completed_calls ?? "–"}</div><div className="stat-label">Completed</div></div>
            <div className="stat"><div className="stat-num">{stats?.avg_duration ?? "–"}</div><div className="stat-label">Avg sec</div></div>
            <div className="stat"><div className="stat-num">{stats?.leads ?? "–"}</div><div className="stat-label">Leads</div></div>
            <div className="stat"><div className="stat-num">{stats?.campaigns ?? "–"}</div><div className="stat-label">Campaigns</div></div>
          </div>
        </header>
        {ready ? children : <div className="muted">Loading…</div>}
      </main>
    </div>
  );
}
