import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useEntities } from '@nekazari/module-kit';
import { useSoilApi, type LeafImportResult, type ZoningSummary } from '../hooks/useSoilApi';

interface ParcelEntity {
  id: string;
  type: string;
  [key: string]: unknown;
}

function parcelName(p: ParcelEntity): string {
  const name = p.name as { value?: string } | string | undefined;
  return typeof name === 'string' ? name : name?.value || p.id.split(':').pop() || p.id;
}

/** Leaf (plant tissue) lab analyses: CSV import with a preview, and a per-zone CSV export. */
export function LeafAnalysesTab() {
  const { t } = useTranslation('soil');
  const api = useSoilApi();
  const { data: parcels } = useEntities<ParcelEntity>('AgriParcel');
  const [parcelId, setParcelId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<LeafImportResult | null>(null);
  const [written, setWritten] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [zonings, setZonings] = useState<ZoningSummary[]>([]);
  const [zoning, setZoning] = useState('');

  useEffect(() => {
    setZonings([]); setZoning(''); setPreview(null); setFile(null); setWritten(null); setError(null);
    if (!parcelId) return;
    let cancelled = false;
    api.listZonings(parcelId)
      .then((zs) => {
        if (cancelled) return;
        setZonings(zs);
        setZoning(zs.find((z) => z.is_default)?.run_id ?? '');
      })
      .catch(() => { if (!cancelled) setZonings([]); });
    return () => { cancelled = true; };
  }, [parcelId, api]);

  const form = (f: File) => { const fd = new FormData(); fd.append('file', f); return fd; };

  const onFile = async (f: File) => {
    setFile(f); setPreview(null); setWritten(null); setError(null); setBusy(true);
    try {
      setPreview(await api.previewLeafCsv(parcelId, form(f)));
    } catch (e) {
      setError((e as { message?: string })?.message || t('leaf.previewFailed'));
    } finally {
      setBusy(false);
    }
  };

  const doImport = async () => {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const res = await api.importLeafCsv(parcelId, form(file));
      setWritten(res.created);
      setPreview(res.rejected.length ? res : null);
    } catch (e) {
      setError((e as { message?: string })?.message || t('leaf.importFailed'));
    } finally {
      setBusy(false);
    }
  };

  const doExport = async () => {
    setError(null);
    try {
      const blob = await api.exportLeafCsv(parcelId, zoning || undefined);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `leaf-analyses-${parcelId.split(':').pop()}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(t('leaf.exportFailed'));
    }
  };

  return (
    <div className="bg-nkz-surface rounded-nkz-md p-6 space-y-4">
      <h2 className="text-nkz-lg font-medium">{t('leaf.title')}</h2>
      <p className="text-nkz-sm text-nkz-muted">{t('leaf.intro')}</p>

      <label className="block">
        <span className="text-nkz-sm text-nkz-muted">{t('leaf.parcel')}</span>
        <select aria-label={t('leaf.parcel')} value={parcelId} onChange={(e) => setParcelId(e.target.value)}
          className="w-full mt-1 rounded-nkz-sm border border-nkz-border bg-nkz-surface px-3 py-2 text-nkz-sm">
          <option value="">{t('leaf.choose')}</option>
          {(parcels || []).map((p) => <option key={p.id} value={p.id}>{parcelName(p)}</option>)}
        </select>
      </label>

      {!parcelId && <p className="text-nkz-sm text-nkz-muted">{t('leaf.chooseParcel')}</p>}

      {parcelId && (
        <>
          <div>
            <label htmlFor="leaf-file" className="text-nkz-sm text-nkz-muted">{t('leaf.file')}</label>
            <input id="leaf-file" type="file" accept=".csv" disabled={busy} className="block w-full text-nkz-sm mt-1"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void onFile(f); e.target.value = ''; }} />
            <p className="text-nkz-xs text-nkz-muted mt-1">{t('leaf.format')}</p>
          </div>

          {error && <p className="text-nkz-sm text-nkz-danger" role="alert">{error}</p>}
          {written !== null && <p className="text-nkz-sm text-nkz-success" role="status">{t('leaf.imported', { count: written })}</p>}

          {preview && (
            <div className="space-y-2">
              <p className="text-nkz-sm">{t('leaf.previewCounts', { accepted: preview.accepted.length, rejected: preview.rejected.length })}</p>
              {preview.rejected.length > 0 && (
                <ul className="text-nkz-xs text-nkz-danger" data-testid="leaf-rejected">
                  {preview.rejected.map((r) => <li key={`${r.row}-${r.error}`}>{r.error}</li>)}
                </ul>
              )}
              {preview.warnings.length > 0 && (
                <ul className="text-nkz-xs text-nkz-muted">
                  {preview.warnings.map((w) => <li key={w.column}>{t('leaf.ignoredColumn', { column: w.column })}</li>)}
                </ul>
              )}
              {written === null && (
                <button type="button" disabled={busy || preview.accepted.length === 0} onClick={() => { void doImport(); }}
                  className="px-4 py-2 rounded-nkz-sm bg-nkz-accent-base text-white text-nkz-sm disabled:opacity-50">
                  {t('leaf.import')}
                </button>
              )}
            </div>
          )}

          <div className="border-t border-nkz-border pt-4 space-y-2">
            <label className="block">
              <span className="text-nkz-sm text-nkz-muted">{t('leaf.zoning')}</span>
              <select aria-label={t('leaf.zoning')} value={zoning} onChange={(e) => setZoning(e.target.value)}
                className="w-full mt-1 rounded-nkz-sm border border-nkz-border bg-nkz-surface px-3 py-2 text-nkz-sm">
                <option value="">{t('leaf.noZoning')}</option>
                {zonings.map((z) => (
                  <option key={z.run_id} value={z.run_id}>
                    {t('leaf.zoningOption', { method: z.method ?? '', date: (z.date ?? '').slice(0, 10), count: z.zone_count })}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" onClick={() => { void doExport(); }}
              className="px-4 py-2 rounded-nkz-sm border border-nkz-border text-nkz-sm hover:bg-nkz-muted/5">
              {t('leaf.export')}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
