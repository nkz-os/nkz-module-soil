import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useEntities } from '@nekazari/module-kit';
import { useSoilApi, type LeafImportResult, type LeafSample, type ZoningSummary } from '../hooks/useSoilApi';

interface ParcelEntity {
  id: string;
  type: string;
  [key: string]: unknown;
}

function parcelName(p: ParcelEntity): string {
  const name = p.name as { value?: string } | string | undefined;
  return typeof name === 'string' ? name : name?.value || p.id.split(':').pop() || p.id;
}

/** Export value meaning "no zone column"; an absent value means the default zoning. */
const NO_ZONING = 'none';
const WARNING_KEYS: Record<string, string> = {
  ignored_column: 'leaf.ignoredColumn',
  stored_as_other: 'leaf.storedAsOther',
  stale_not_removed: 'leaf.staleNotRemoved',
};

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
  const [zoning, setZoning] = useState(NO_ZONING);
  const [replaceOld, setReplaceOld] = useState(true);
  const [samples, setSamples] = useState<LeafSample[]>([]);
  const [confirming, setConfirming] = useState<string | null>(null);

  const loadSamples = React.useCallback(async (id: string) => {
    try {
      setSamples(await api.listLeafSamples(id));
    } catch {
      setSamples([]);
    }
  }, [api]);

  useEffect(() => {
    setZonings([]); setZoning(NO_ZONING); setPreview(null); setFile(null); setWritten(null); setError(null);
    setSamples([]); setConfirming(null);
    if (!parcelId) return;
    void loadSamples(parcelId);
    let cancelled = false;
    api.listZonings(parcelId)
      .then((zs) => {
        if (cancelled) return;
        setZonings(zs);
        setZoning(zs.find((z) => z.is_default)?.run_id ?? NO_ZONING);
      })
      .catch(() => { if (!cancelled) setZonings([]); });
    return () => { cancelled = true; };
  }, [parcelId, api, loadSamples]);

  const form = (f: File) => { const fd = new FormData(); fd.append('file', f); return fd; };

  const onFile = async (f: File) => {
    setFile(f); setPreview(null); setWritten(null); setError(null); setReplaceOld(true); setBusy(true);
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
      const res = await api.importLeafCsv(parcelId, form(file), corrections > 0 && replaceOld);
      setWritten(res.created);
      setPreview(res.rejected.length ? res : null);
      void loadSamples(parcelId);
    } catch (e) {
      setError((e as { message?: string })?.message || t('leaf.importFailed'));
    } finally {
      setBusy(false);
    }
  };

  const doExport = async () => {
    setError(null);
    try {
      const blob = await api.exportLeafCsv(parcelId, zoning);
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

  const updates = preview ? preview.accepted.filter((a) => a.action === 'update').length : 0;
  const corrections = preview ? preview.accepted.filter((a) => (a.replaces ?? []).length > 0).length : 0;

  const doDelete = async (id: string) => {
    setConfirming(null); setError(null);
    try {
      await api.deleteLeafSample(id);
      await loadSamples(parcelId);
    } catch {
      setError(t('leaf.deleteFailed'));
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
              {updates > 0 && <p className="text-nkz-sm text-nkz-muted">{t('leaf.updates', { count: updates })}</p>}
              {corrections > 0 && written === null && (
                <div className="space-y-1">
                  <p className="text-nkz-sm text-nkz-muted">{t('leaf.corrections', { count: corrections })}</p>
                  <label className="flex items-center gap-2 text-nkz-sm">
                    <input type="checkbox" checked={replaceOld} onChange={(e) => setReplaceOld(e.target.checked)} />
                    {t('leaf.replaceOld')}
                  </label>
                </div>
              )}
              {preview.warnings.length > 0 && (
                <ul className="text-nkz-xs text-nkz-muted">
                  {preview.warnings.map((w, i) => <li key={`${w.code}-${w.column}-${i}`}>{t(WARNING_KEYS[w.code] ?? 'leaf.ignoredColumn', { column: w.column })}</li>)}
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
            <h3 className="text-nkz-sm font-medium">{t('leaf.samples')}</h3>
            {samples.length === 0 ? (
              <p className="text-nkz-sm text-nkz-muted">{t('leaf.noSamples')}</p>
            ) : (
              <ul className="text-nkz-sm divide-y divide-nkz-border">
                {samples.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-2 py-1">
                    <span>
                      {(s.dateSampled ?? '')} · <span className="font-medium">{s.sampleCode}</span> · {s.plantTissue} · {s.plantCodes.join(', ')}
                    </span>
                    {confirming === s.id ? (
                      <span className="flex items-center gap-2">
                        <span className="text-nkz-muted">{t('leaf.confirmDelete')}</span>
                        <button type="button" onClick={() => { void doDelete(s.id); }}
                          className="px-2 py-1 rounded-nkz-sm bg-nkz-danger text-white text-nkz-xs">{t('leaf.yes')}</button>
                        <button type="button" onClick={() => setConfirming(null)}
                          className="px-2 py-1 rounded-nkz-sm border border-nkz-border text-nkz-xs">{t('leaf.no')}</button>
                      </span>
                    ) : (
                      <button type="button" onClick={() => setConfirming(s.id)}
                        className="px-2 py-1 rounded-nkz-sm border border-nkz-border text-nkz-xs hover:bg-nkz-muted/5">{t('leaf.delete')}</button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="border-t border-nkz-border pt-4 space-y-2">
            <label className="block">
              <span className="text-nkz-sm text-nkz-muted">{t('leaf.zoning')}</span>
              <select aria-label={t('leaf.zoning')} value={zoning} onChange={(e) => setZoning(e.target.value)}
                className="w-full mt-1 rounded-nkz-sm border border-nkz-border bg-nkz-surface px-3 py-2 text-nkz-sm">
                <option value={NO_ZONING}>{t('leaf.noZoning')}</option>
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
