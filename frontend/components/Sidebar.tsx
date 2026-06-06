"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const NAV = [
  { href: "/dashboard", icon: "📊", label: "Dashboard" },
  { href: "/dialer", icon: "📞", label: "Dialer" },
  { href: "/leads", icon: "👥", label: "Leads" },
  { href: "/campaigns", icon: "📣", label: "Campaigns" },
  { href: "/analytics", icon: "📈", label: "Analytics" },
  { href: "/logs", icon: "🗂️", label: "Call Logs" },
];

export default function Sidebar({ connected }: { connected: boolean }) {
  const pathname = usePathname();
  const router = useRouter();

  async function logout() {
    try { await fetch("/api/logout", { method: "POST" }); } catch {}
    router.push("/login");
  }

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">MU</div>
        <div>
          <div className="brand-title">Voice Agent</div>
          <div className="brand-sub">Admission Console</div>
        </div>
      </div>
      <nav className="nav">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href}
                className={"nav-item" + (pathname === n.href ? " active" : "")}>
            <span>{n.icon}</span> {n.label}
          </Link>
        ))}
      </nav>
      <div className="sidebar-foot">
        <span className={"dot " + (connected ? "ok" : "bad")} />
        <span>{connected ? "connected" : "offline"}</span>
      </div>
      <button className="logout" onClick={logout}>⎋ Sign out</button>
    </aside>
  );
}
