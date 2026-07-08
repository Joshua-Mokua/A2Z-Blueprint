// ──────────────────────────────────────────────────────────────────────────
// DocumentViewerModal — read a deal document WITHIN the system.
//
// Renders the document inline (no download needed for a read): PDFs and images
// render natively; text files render as text. Word/Excel and other binary
// formats have no native browser preview, so they fall back to a download
// prompt (a future enhancement can render .docx via a converter).
//
// `canDownload` gates the download affordance: relationship owners / analysts
// get it; committee members read but cannot download (they see a note instead).
// ──────────────────────────────────────────────────────────────────────────
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button } from '@/components/Button';
import { downloadDealDocument } from '@/lib/api';

type Kind = 'pdf' | 'image' | 'text' | 'other';

function kindOf(filename: string): Kind {
  const ext = (filename.toLowerCase().split('.').pop() || '');
  if (ext === 'pdf') return 'pdf';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(ext)) return 'image';
  if (['txt', 'csv', 'json', 'md', 'log'].includes(ext)) return 'text';
  return 'other';
}

export function DocumentViewerModal({
  dealId, docName, filename, canDownload = true, onClose,
}: {
  dealId: string;
  docName: string;
  filename: string;
  canDownload?: boolean;
  onClose: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const kind = kindOf(filename);

  useEffect(() => {
    let alive = true;
    let objUrl: string | null = null;
    (async () => {
      try {
        const blob = await downloadDealDocument(dealId, docName);
        if (!alive) return;
        if (kind === 'text') {
          setText(await blob.text());
        } else {
          objUrl = URL.createObjectURL(blob);
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

  const doDownload = () => {
    let href = url;
    let revoke = false;
    if (!href && text != null) {
      href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
      revoke = true;
    }
    if (!href) return;
    const a = document.createElement('a');
    a.href = href; a.download = filename; a.click();
    if (revoke) setTimeout(() => URL.revokeObjectURL(href as string), 10000);
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="relative flex h-[85vh] w-full max-w-4xl flex-col rounded-lg border border-gray-200 bg-white shadow-xl">
        <div className="flex items-center justify-between gap-3 border-b border-gray-200 px-5 py-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-gray-900">{docName}</div>
            <div className="truncate text-xs text-gray-500">{filename}</div>
          </div>
          <div className="flex items-center gap-2">
            {canDownload && !loading && !error && (
              <Button variant="ghost" size="sm" onClick={doDownload}>Download</Button>
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
          {!loading && !error && kind === 'other' && (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
              <div className="text-sm text-gray-600">
                In-app preview isn’t available for this file type yet.
              </div>
              {canDownload
                ? <Button onClick={doDownload}>Download to read</Button>
                : <div className="text-xs text-gray-400">Download is not permitted for your role.</div>}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
