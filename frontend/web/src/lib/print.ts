// Shared print helper — opens a clean, print-styled window and triggers the
// browser print dialog. Mirrors the Affordability appraisal print approach so
// all printable artifacts (CR, Case Journey, appraisal) share one look.

export function escapeHtml(v: unknown): string {
  return String(v ?? '').replace(
    /[&<>]/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c] as string),
  );
}

export function printDocument(title: string, bodyHtml: string): void {
  const html = `<!doctype html><html><head><meta charset="utf-8"/><title>${escapeHtml(title)}</title>
<style>
  body{font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;margin:32px;font-size:12px}
  h1{font-size:18px;margin:0 0 2px}
  h2{font-size:13px;margin:18px 0 6px;border-bottom:1px solid #ccc;padding-bottom:2px}
  table{width:100%;border-collapse:collapse;margin:6px 0}
  th,td{border:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}
  th{background:#f3f3f3}
  .muted{color:#666;font-weight:normal}
  .head{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #0082BB;padding-bottom:6px;margin-bottom:8px}
  @media print{body{margin:12mm}}
</style></head><body>${bodyHtml}
<script>window.onload=function(){window.print();}</script></body></html>`;
  const w = window.open('', '_blank');
  if (w) {
    w.document.write(html);
    w.document.close();
  }
}
