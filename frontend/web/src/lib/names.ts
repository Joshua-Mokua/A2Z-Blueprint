// Shared staff-name display helpers — one place so every surface agrees.
//
// A person's legal full name (e.g. "Rabecca Mueni Mbithi") is kept intact, but is
// rarely what we show:
//   displayName    -> first name only            "Rabecca"        (UI everywhere)
//   analyticsName  -> first + last               "Rabecca Mbithi" (scorecards/analytics)
//
// When the backend supplies an explicit display_name / analytics_name (it derives
// these from a metadata preferred_name — e.g. the MD drops "Mueni"), that WINS.
// Otherwise we derive from the full name so nothing ever renders blank.

function tokens(name?: string | null): string[] {
  return String(name ?? "").replace(/,/g, " ").split(/\s+/).filter(Boolean);
}

/** First name for the UI. Prefers an explicit display_name from the backend. */
export function displayName(full?: string | null, explicit?: string | null): string {
  const e = String(explicit ?? "").trim();
  if (e) return tokens(e)[0] ?? e;
  const t = tokens(full);
  return t[0] ?? String(full ?? "").trim();
}

/** First + last for analytics. Prefers an explicit analytics_name from the backend. */
export function analyticsName(full?: string | null, explicit?: string | null): string {
  const e = String(explicit ?? "").trim();
  if (e) return e;
  const t = tokens(full);
  if (t.length >= 2) return `${t[0]} ${t[t.length - 1]}`;
  return t[0] ?? String(full ?? "").trim();
}

/** Convenience for an object that may carry any of the known name fields. */
export function nameOf(
  o: {
    display_name?: string | null;
    analytics_name?: string | null;
    full_name?: string | null;
    staff_name?: string | null;
    name?: string | null;
  } | null | undefined,
  mode: "display" | "analytics" = "display",
): string {
  if (!o) return "";
  const full = o.full_name ?? o.staff_name ?? o.name ?? "";
  return mode === "analytics"
    ? analyticsName(full, o.analytics_name)
    : displayName(full, o.display_name);
}
