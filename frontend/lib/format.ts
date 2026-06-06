export const fmtTime = (epoch?: number) =>
  epoch
    ? new Date(epoch * 1000).toLocaleString([], { dateStyle: "short", timeStyle: "short" })
    : "—";

export const fmtDur = (s?: number) => (s ? `${s}s` : "—");
export const dirIcon = (d?: string) => (d === "outbound" ? "↗️" : "↘️");

export const STATUS_COLORS: Record<string, string> = {
  completed: "#16a34a", "in-progress": "#2563eb", ringing: "#2563eb",
  queued: "#6366f1", initiated: "#6366f1", answered: "#2563eb",
  failed: "#dc2626", busy: "#d97706", "no-answer": "#d97706",
  canceled: "#9ca3af", unknown: "#9ca3af",
};

export const LEAD_COLORS: Record<string, string> = {
  new: "#6366f1", contacted: "#2563eb", interested: "#d97706",
  enrolled: "#16a34a", lost: "#dc2626",
};

export const colorFor = (k: string, map: Record<string, string>) => map[k] || "#8a90a6";

export type DayPoint = { day: string; total: number; completed: number };

// Fill a fixed window of `n` days (incl. empty days) from sparse rows.
export function fillDays(rows: DayPoint[], n: number): DayPoint[] {
  const byDay: Record<string, DayPoint> = Object.fromEntries(rows.map((r) => [r.day, r]));
  const out: DayPoint[] = [];
  const now = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(now.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    out.push(byDay[key] || { day: key, total: 0, completed: 0 });
  }
  return out;
}
