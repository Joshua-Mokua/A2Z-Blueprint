// ──────────────────────────────────────────────────────────────────────────
// DocumentViewerModal — read a deal document WITHIN the system.
//
// Renders the document inline (no download needed for a read):
//   • PDF                    → native inline (iframe)
//   • images                 → native inline (img)
//   • text / csv / json / md → inline text
//   • .docx                  → converted to HTML via mammoth (lazy-loaded)
//   • .xlsx / .xls           → converted to HTML tables via SheetJS (lazy-loaded)
//   • other (e.g. .pptx)     → download-to-read fallback (no native preview)
//
// `canDownload` gates the download affordance: relationship owners / analysts
// get it; committee members read but cannot download (a note shows instead).
// ──────────────────────────────────────────────────────────────────────────
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button } from '@/components/Button';
import { downloadDealDocument } from '@/lib/api';

type Kind = 'pdf' | 'image' | 'text' | 'docx' | 'xlsx' | 'other';

function kindOf(filename: string): Kind {
  const ext = (filename.toLowerCase().split('.').pop() || '');
  if (ext === 'pdf') return 'pdf';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(ext)) return 'image';
  if (['txt', 'csv', 'json', 'md', 'log'].includes(ext)) return 'text';
  if (ext === 'docx') return 'docx';
  if (['xlsx', 'xls'].includes(ext)) return 'xlsx';
  return 'other';
}

export function DocumentViewerModal({
  dealId, docName, filename, canDownload = true, onClose, fetchBlob,
}: {
  dealId: string;
  docName: string;
  filename: string;
  canDownload?: boolean;
  onClose: () => void;
  /** Optional custom fetcher (e.g. LMS-side download). Defaults to the deal document route. */
  fetchBlob?: () => Promise<Blob>;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const kind = kindOf(filename);
  const doFetch = fetchBlob ?? (() => downloadDealDocument(dealId, docName));

  useEffect(() => {
    let alive = true;
    let objUrl: string | null = null;
    (async () => {
      try {
        const blob = await doFetch();
        if (!alive) return;
        if (kind === 'text') {
          setText(await blob.text());
        } else if (kind === 'docx') {
          const buf = await blob.arrayBuffer();
          const mod: any = await import('mammoth');
          const mammoth = mod.default ?? mod;
          const { value } = await mammoth.convertToHtml({ arrayBuffer: buf });
          if (alive) setHtml(value || '<p><em>Empty document.</em></p>');
        } else if (kind === 'xlsx') {
          const buf = await blob.arrayBuffer();
          const XLSX: any = await import('xlsx');
          const wb = XLSX.read(buf, { type: 'array' });
          const parts = (wb.SheetNames as string[]).map((name) =>
            `<h3>${name}</h3>${XLSX.utils.sheet_to_html(wb.Sheets[name])}`);
          if (alive) setHtml(parts.join('\n') || '<p><em>Empty workbook.</em></p>');
        } else {
          // The download endpoint serves application/octet-stream, which a PDF
          // <iframe> will not render — re-type PDFs so the browser renders them
          // inline. Images render fine from any blob (the browser sniffs them).
          const src = kind === 'pdf'
            ? new Blob([await blob.arrayBuffer()], { type: 'application/pdf' })
            : blob;
          objUrl = URL.createObjectURL(src);
          setUrl(objUrl);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Could not load document');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; if (objUrl) URL.revokeObjectURL(objUrl); };
  }, [dealId, docName, kind]);

  const doDownload = async () => {
    try {
      const blob = await doFetch();
      const href = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href; a.download = filename; a.click();
      setTimeout(() => URL.revokeObjectURL(href), 10000);
    } catch {
      setError('Download failed.');
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="relative flex h-[94vh] w-full max-w-[95vw] flex-col rounded-lg border border-gray-200 bg-white shadow-xl">
        <div className="flex items-center justify-between gap-3 border-b border-gray-200 px-5 py-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-gray-900">{docName}</div>
            <div className="truncate text-xs text-gray-500">{filename}</div>
          </div>
          <div className="flex items-center gap-2">
            {canDownload && !loading && (
              <Button variant="ghost" size="sm" onClick={() => void doDownload()}>Download</Button>
            )}
            <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
          </div>
        </div>
        <div className="flex-1 overflow-auto bg-gray-50">
          {loading && <div className="p-6 text-sm text-gray-500">Loading…</div>}
          {error && <div className="p-6 text-sm text-red-600">{error}</div>}
          {!loading && !error && kind === 'pdf' && url && (
            <iframe title={docName} src={url} className="h-full w-full" />
          )}
          {!loading && !error && kind === 'image' && url && (
            <div className="flex h-full items-center justify-center p-4">
              <img src={url} alt={docName} className="max-h-full max-w-full object-contain" />
            </div>
          )}
          {!loading && !error && kind === 'text' && text != null && (
            <pre className="whitespace-pre-wrap p-5 text-xs text-gray-800">{text}</pre>
          )}
          {!loading && !error && (kind === 'docx' || kind === 'xlsx') && html != null && (
            <div className="doc-html bg-white p-6 text-sm text-gray-800">
              <style>{`
                .doc-html table { border-collapse: collapse; margin: 0.5rem 0; }
                .doc-html td, .doc-html th { border: 1px solid #d1d5db; padding: 4px 8px; }
                .doc-html h1, .doc-html h2 { font-weight: 600; margin: 0.75rem 0 0.4rem; }
                .doc-html h3 { font-weight: 600; margin: 0.75rem 0 0.3rem; color: #005B82; }
                .doc-html p { margin: 0.35rem 0; }
                .doc-html ul, .doc-html ol { margin: 0.35rem 0 0.35rem 1.25rem; }
              `}</style>
              <div dangerouslySetInnerHTML={{ __html: html }} />
            </div>
          )}
          {!loading && !error && kind === 'other' && (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
              <div className="text-sm text-gray-600">
                In-app preview isn’t available for this file type yet.
              </div>
              {canDownload
                ? <Button onClick={() => void doDownload()}>Download to read</Button>
                : <div className="text-xs text-gray-400">Download is not permitted for your role.</div>}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
