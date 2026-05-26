import React, { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { SlotShellCompact } from '@nekazari/viewer-kit';
import { useSearchParams } from 'react-router-dom';
import { useSoilApi } from '../hooks/useSoilApi';
import { useEntities } from '@nekazari/module-kit';

type Tab = 'dashboard' | 'manual' | 'csv' | 'history';

// ─── Types ───────────────────────────────────────────────────────────────

interface SoilHorizon {
  depthFrom: number;
  depthTo: number;
  sand?: number;
  silt?: number;
  clay?: number;
  organicCarbon?: number;
  bulkDensity?: number;
  ph?: number;
  ksatSaturated?: number;
  availableWaterCapacity?: number;
  fieldCapacity?: number;
  wiltingPoint?: number;
  hydrologicGroup?: string;
  usdaTextureClass?: string;
  penetrationResistance?: number;
}

interface CompactionEntry {
  depthFrom: number;
  depthTo: number;
  value: number;
  classification: string;
}

interface AgriSoilEntity {
  id: string;
  type: string;
  [key: string]: unknown;
  refAgriParcel?: { type: string; object: string };
  dataSource?: { type: string; value: string };
  uncertainty?: { type: string; value: number };
  horizons?: { type: string; value: SoilHorizon[] };
  relativeCompaction?: { type: string; value: CompactionEntry[] };
  location?: { type: string; value: Record<string, unknown> };
}

interface NgsiLdEntity {
  id: string;
  type: string;
  [key: string]: unknown;
}

// ─── Texture Triangle SVG Component ──────────────────────────────────────

// Texture class is computed by the backend (usdaTextureClass) and passed in.
// Raw fractions may be suppressed (license) -> plot the point only when present,
// but always show the derived class label.
function TextureTriangle({ sand, silt, clay, textureClass }: {
  sand?: number; silt?: number; clay?: number; textureClass?: string;
}) {
  const total = (sand || 0) + (silt || 0) + (clay || 0);
  const hasFractions = total >= 1;
  const si = hasFractions ? (silt || 0) / total : 0;
  const c = hasFractions ? (clay || 0) / total : 0;
  const x = 0.5 * si + c;
  const y = (Math.sqrt(3) / 2) * si;

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 100 90" className="w-32 h-28">
        <polygon
          points="50,5 5,85 95,85"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
          className="text-nkz-border"
        />
        <text x="50" y="3" textAnchor="middle" className="fill-nkz-muted" fontSize="5">Arena</text>
        <text x="0" y="90" textAnchor="start" className="fill-nkz-muted" fontSize="5">Arcilla</text>
        <text x="100" y="90" textAnchor="end" className="fill-nkz-muted" fontSize="5">Limo</text>
        {hasFractions && (
          <circle cx={x * 90 + 5} cy={y * 80 + 5} r="3" className="fill-nkz-primary" />
        )}
      </svg>
      <span className="text-nkz-xs text-nkz-muted mt-1">{textureClass || '—'}</span>
    </div>
  );
}

// ─── Refresh / compute soil for a parcel ─────────────────────────────────

function RefreshSoilButton({ parcelId }: { parcelId: string }) {
  const { t } = useTranslation('soil');
  const api = useSoilApi();
  const [state, setState] = useState<'idle' | 'busy' | 'done' | 'error'>('idle');

  const onClick = async () => {
    if (!parcelId) return;
    setState('busy');
    try {
      await api.forceIngest(parcelId);
      setState('done');
    } catch {
      setState('error');
    }
  };

  const label =
    state === 'busy' ? t('refresh.busy', 'Calculando…')
    : state === 'done' ? t('refresh.done', 'Encolado ✓')
    : state === 'error' ? t('refresh.error', 'Error')
    : t('refresh.action', 'Calcular suelo');

  return (
    <button
      onClick={onClick}
      disabled={state === 'busy' || !parcelId}
      className="px-3 py-1.5 text-nkz-xs rounded-nkz-sm border border-nkz-border hover:border-nkz-primary disabled:opacity-50"
    >
      {label}
    </button>
  );
}

// ─── Module Page ─────────────────────────────────────────────────────────

export default function ModulePage() {
  const { t } = useTranslation('soil');
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const [searchParams] = useSearchParams();

  useEffect(() => {
    if (searchParams.get('parcel')) {
      setActiveTab('dashboard');
    }
  }, [searchParams]);

  const tabs: { id: Tab; label: string }[] = [
    { id: 'dashboard', label: t('tabs.dashboard') },
    { id: 'manual', label: t('tabs.manual') },
    { id: 'csv', label: t('tabs.csv') },
    { id: 'history', label: t('tabs.history') },
  ];

  return (
    <SlotShellCompact moduleId="soil">
      <div className="max-w-5xl mx-auto p-6 space-y-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-nkz-xl font-medium">{t('title')}</h1>
        </div>
        <div className="flex gap-2 border-b border-nkz-border">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-nkz-sm border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-nkz-primary text-nkz-primary'
                  : 'border-transparent text-nkz-muted hover:text-nkz-text'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === 'dashboard' && <DashboardTab />}
        {activeTab === 'manual' && <ManualSamplingTab />}
        {activeTab === 'csv' && <CsvUploadTab />}
        {activeTab === 'history' && <HistoryTab />}
      </div>
    </SlotShellCompact>
  );
}

// ─── Dashboard Tab ───────────────────────────────────────────────────────

function DashboardTab() {
  const { t } = useTranslation('soil');
  const api = useSoilApi();
  const { data: soils, isLoading: soilsLoading } = useEntities<AgriSoilEntity>('AgriSoilExtended');
  const [selectedParcel, setSelectedParcel] = useState<string | null>(null);
  const [summary, setSummary] = useState<AgriSoilEntity | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    const parcelQuery = searchParams.get('parcel');
    if (parcelQuery && parcelQuery !== selectedParcel) {
      setSelectedParcel(parcelQuery);
    }
  }, [searchParams, selectedParcel]);

  const handleSelectParcel = (id: string) => {
    setSelectedParcel(id);
    setSearchParams(prev => { prev.set('parcel', id); return prev; }, { replace: true });
  };

  // Fetch summary when parcel selected
  useEffect(() => {
    if (selectedParcel) {
      api.getSummary(selectedParcel).then((data: unknown) => setSummary(data as AgriSoilEntity)).catch(() => setSummary(null));
    }
  }, [selectedParcel, api]);

  const filteredSoils = React.useMemo(() => {
    if (!soils) return [];
    if (!searchTerm) return soils;
    const lower = searchTerm.toLowerCase();
    return soils.filter(s => {
      const parcelId = s.refAgriParcel?.object?.split(':').pop() || s.id;
      const dataSource = s.dataSource?.value || '';
      return parcelId.toLowerCase().includes(lower) || String(dataSource).toLowerCase().includes(lower);
    });
  }, [soils, searchTerm]);

  if (soilsLoading) {
    return (
      <div className="bg-nkz-surface rounded-nkz-md p-6">
        <p className="text-nkz-muted text-nkz-sm">{t('loading')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Parcel selector */}
      <div className="bg-nkz-surface rounded-nkz-md p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between mb-4 gap-4">
          <h2 className="text-nkz-lg font-medium">{t('dashboard.parcels')}</h2>
          <input
            type="search"
            placeholder={t('search', 'Search parcels...')}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="px-3 py-1.5 text-nkz-sm rounded-nkz-sm border border-nkz-border bg-transparent min-w-[200px]"
          />
        </div>
        {filteredSoils && filteredSoils.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-h-[300px] overflow-y-auto pr-2">
            {filteredSoils.map((soil) => {
              const parcelRef = soil.refAgriParcel;
              const parcelId = parcelRef?.object?.split(':').pop() || soil.id;
              const dataSource = soil.dataSource?.value;
              const uncertainty = soil.uncertainty?.value;
              const horizonList = soil.horizons?.value || [];
              const topH = horizonList[0] || {};

              return (
                <button
                  key={soil.id}
                  onClick={() => handleSelectParcel(soil.id)}
                  className={`text-left p-4 rounded-nkz-md border transition-colors ${
                    selectedParcel === soil.id
                      ? 'border-nkz-primary bg-nkz-primary/5'
                      : 'border-nkz-border hover:border-nkz-primary/50'
                  }`}
                >
                  <div className="text-nkz-sm font-medium truncate">{parcelId}</div>
                  <div className="text-nkz-xs text-nkz-muted mt-1">
                    {dataSource || '—'}
                    {uncertainty != null && (
                      <span className="ml-2">σ={uncertainty.toFixed(2)}</span>
                    )}
                  </div>
                  {(topH.hydrologicGroup || topH.ksatSaturated) && (
                    <div className="flex gap-3 mt-2 text-nkz-xs">
                      {topH.hydrologicGroup && (
                        <span className="text-nkz-muted">
                          {t('hydrologicGroup')}: <span className="font-medium">{String(topH.hydrologicGroup)}</span>
                        </span>
                      )}
                      {topH.ksatSaturated != null && (
                        <span className="text-nkz-muted">
                          Ksat: <span className="font-medium">{String(topH.ksatSaturated)} mm/h</span>
                        </span>
                      )}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-8">
            <p className="text-nkz-muted text-nkz-sm">{t('dashboard.noSoilData')}</p>
            <p className="text-nkz-xs text-nkz-muted mt-2">{t('dashboard.noSoilHint')}</p>
          </div>
        )}
      </div>

      {/* Selected parcel detail */}
      {summary && selectedParcel && (
        <div className="bg-nkz-surface rounded-nkz-md p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-nkz-lg font-medium">{t('dashboard.detail')}</h2>
            <RefreshSoilButton parcelId={summary.refAgriParcel?.object?.split(':').pop() || ''} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Texture triangle */}
            {summary.horizons?.value?.[0] && (
              <div className="flex flex-col items-center">
                <h3 className="text-nkz-sm font-medium mb-2">{t('dashboard.texture')}</h3>
                <TextureTriangle
                  sand={summary.horizons.value[0].sand}
                  silt={summary.horizons.value[0].silt}
                  clay={summary.horizons.value[0].clay}
                  textureClass={summary.horizons.value[0].usdaTextureClass}
                />
              </div>
            )}

            {/* Pedotransfer results */}
            <div className="space-y-2">
              <h3 className="text-nkz-sm font-medium mb-2">{t('dashboard.properties')}</h3>
              {summary.horizons?.value?.map((h: SoilHorizon) => (
                <div key={`${h.depthFrom}-${h.depthTo}`} className="text-nkz-xs space-y-1 border-b border-nkz-border/50 pb-2">
                  <div className="font-medium text-nkz-muted">{h.depthFrom}–{h.depthTo} cm</div>
                  {h.usdaTextureClass && (
                    <div className="flex justify-between">
                      <span>{t('textureClass', 'Texture class')}</span>
                      <span className="font-medium">{h.usdaTextureClass}</span>
                    </div>
                  )}
                  {h.hydrologicGroup && (
                    <div className="flex justify-between">
                      <span>{t('hydrologicGroup')}</span>
                      <span className="font-medium">{h.hydrologicGroup}</span>
                    </div>
                  )}
                  {h.ksatSaturated != null && (
                    <div className="flex justify-between">
                      <span>{t('ksat')}</span>
                      <span className="font-medium">{h.ksatSaturated} mm/h</span>
                    </div>
                  )}
                  {h.availableWaterCapacity != null && (
                    <div className="flex justify-between">
                      <span>{t('awc')}</span>
                      <span className="font-medium">{(h.availableWaterCapacity * 100).toFixed(1)}%</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Compaction */}
          {summary.relativeCompaction?.value && summary.relativeCompaction.value.length > 0 && (
            <div className="mt-4 pt-4 border-t border-nkz-border">
              <h3 className="text-nkz-sm font-medium mb-2">{t('compaction')}</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {summary.relativeCompaction.value.map((rc: CompactionEntry) => (
                  <div key={`${rc.depthFrom}-${rc.depthTo}`} className="text-nkz-xs text-center p-2 rounded-nkz-sm bg-nkz-muted/10">
                    <div className="font-medium">{rc.depthFrom}–{rc.depthTo} cm</div>
                    <div className={`${compactionColor(rc.classification)}`}>
                      {rc.classification} ({rc.value}%)
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Attribution */}
          <div className="mt-4 pt-4 border-t border-nkz-border text-nkz-xs text-nkz-muted">
            {t('source')}: {summary.dataSource?.value || '—'}
            {summary.uncertainty?.value != null && (
              <span className="ml-4">
                {t('uncertainty')}: {String(summary.uncertainty.value)}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function compactionColor(classification: string): string {
  switch (classification) {
    case 'normal': return 'text-nkz-success';
    case 'slight': return 'text-nkz-warning';
    case 'moderate': return 'text-orange-500';
    case 'severe': return 'text-nkz-danger';
    default: return 'text-nkz-muted';
  }
}

// ─── Manual Sampling Tab ─────────────────────────────────────────────────

function ManualSamplingTab() {
  const { t } = useTranslation('soil');
  const api = useSoilApi();
  const [result, setResult] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const fields = [
    { key: 'lat', label: t('fields.lat'), type: 'number', required: true },
    { key: 'lon', label: t('fields.lon'), type: 'number', required: true },
    { key: 'depthFrom', label: t('fields.depthFrom'), type: 'number', required: true },
    { key: 'depthTo', label: t('fields.depthTo'), type: 'number', required: true },
    { key: 'sand', label: t('fields.sand'), type: 'number' },
    { key: 'silt', label: t('fields.silt'), type: 'number' },
    { key: 'clay', label: t('fields.clay'), type: 'number' },
    { key: 'organicCarbon', label: t('fields.organicCarbon'), type: 'number' },
    { key: 'ph', label: t('fields.ph'), type: 'number' },
    { key: 'bulkDensity', label: t('fields.bulkDensity'), type: 'number' },
    { key: 'penetrationResistance', label: t('fields.penetrationResistance'), type: 'number' },
    { key: 'samplingDate', label: t('fields.samplingDate'), type: 'date' },
    { key: 'operator', label: t('fields.operator'), type: 'text' },
  ];

  const [form, setForm] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((f) => [f.key, '']))
  );

  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  const validate = useCallback((): string[] => {
    const errors: Record<string, string> = {};

    const lat = parseFloat(form.lat);
    const lon = parseFloat(form.lon);
    if (isNaN(lat) || lat < -90 || lat > 90) errors.lat = t('validation.lat');
    if (isNaN(lon) || lon < -180 || lon > 180) errors.lon = t('validation.lon');

    const depthFrom = parseInt(form.depthFrom);
    const depthTo = parseInt(form.depthTo);
    if (isNaN(depthFrom) || depthFrom < 0) errors.depthFrom = t('validation.depthFrom');
    if (isNaN(depthTo) || depthTo <= depthFrom) errors.depthTo = t('validation.depthTo');

    const sand = form.sand ? parseFloat(form.sand) : null;
    const silt = form.silt ? parseFloat(form.silt) : null;
    const clay = form.clay ? parseFloat(form.clay) : null;
    if (sand !== null && silt !== null && clay !== null) {
      const total = sand + silt + clay;
      if (total < 97 || total > 103) {
        errors.sand = t('validation.textureSum');
      }
    }

    const ph = form.ph ? parseFloat(form.ph) : null;
    if (ph !== null && (ph < 0 || ph > 14)) errors.ph = t('validation.ph');

    const bd = form.bulkDensity ? parseFloat(form.bulkDensity) : null;
    if (bd !== null && (bd < 0.1 || bd > 2.65)) errors.bulkDensity = t('validation.bulkDensity');

    setValidationErrors(errors);
    return Object.values(errors);
  }, [form, t]);

  const handleChange = (field: string, value: string) => {
    setForm((prev: Record<string, string>) => ({ ...prev, [field]: value }));
    // Clear error on change
    if (validationErrors[field]) {
      setValidationErrors((prev: Record<string, string>) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  const handleSubmit = async () => {
    const errors = validate();
    if (errors.length > 0) return;

    try {
      await api.uploadSamplingPoint({
        lat: parseFloat(form.lat),
        lon: parseFloat(form.lon),
        depth_from: parseInt(form.depthFrom),
        depth_to: parseInt(form.depthTo),
        sand: form.sand ? parseFloat(form.sand) : undefined,
        silt: form.silt ? parseFloat(form.silt) : undefined,
        clay: form.clay ? parseFloat(form.clay) : undefined,
        organic_carbon: form.organicCarbon ? parseFloat(form.organicCarbon) : undefined,
        ph: form.ph ? parseFloat(form.ph) : undefined,
        bulk_density: form.bulkDensity ? parseFloat(form.bulkDensity) : undefined,
        penetration_resistance: form.penetrationResistance ? parseFloat(form.penetrationResistance) : undefined,
        sampling_date: form.samplingDate || undefined,
        operator: form.operator || undefined,
      });
      setResult({ type: 'success', message: t('success') });
      setForm(Object.fromEntries(fields.map((f) => [f.key, ''])));
    } catch {
      setResult({ type: 'error', message: t('error') });
    }
  };

  return (
    <div className="bg-nkz-surface rounded-nkz-md p-6">
      <h2 className="text-nkz-lg font-medium mb-4">{t('tabs.manual')}</h2>

      {/* Result banner */}
      {result && (
        <div
          className={`mb-4 p-3 rounded-nkz-sm text-nkz-sm ${
            result.type === 'success'
              ? 'bg-nkz-success/10 text-nkz-success border border-nkz-success/30'
              : 'bg-nkz-danger/10 text-nkz-danger border border-nkz-danger/30'
          }`}
        >
          {result.message}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {fields.map((field) => (
          <div key={field.key}>
            <label className="block text-nkz-xs mb-1">
              {field.label}
              {field.required && <span className="text-nkz-danger ml-1">*</span>}
            </label>
            <input
              type={field.type}
              value={form[field.key]}
              onChange={(e) => handleChange(field.key, e.target.value)}
              className={`w-full border rounded-nkz-sm px-2 py-1 text-nkz-sm ${
                validationErrors[field.key]
                  ? 'border-nkz-danger bg-nkz-danger/5'
                  : 'border-nkz-border'
              }`}
            />
            {validationErrors[field.key] && (
              <p className="text-nkz-xs text-nkz-danger mt-1">{validationErrors[field.key]}</p>
            )}
          </div>
        ))}
      </div>

      <button
        onClick={handleSubmit}
        className="mt-4 px-4 py-2 bg-nkz-primary text-white rounded-nkz-sm text-nkz-sm hover:bg-nkz-primary/90 transition-colors"
      >
        {t('submit')}
      </button>
    </div>
  );
}

// ─── CSV Upload Tab ──────────────────────────────────────────────────────

function CsvUploadTab() {
  const { t } = useTranslation('soil');
  const api = useSoilApi();
  const [result, setResult] = useState<{ type: 'success' | 'error'; message: string; details?: unknown } | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const handleFile = useCallback(
    async (file: File) => {
      setFileName(file.name);
      setUploading(true);
      setResult(null);
      try {
        const formData = new FormData();
        formData.append('file', file);
        const response = await api.uploadCsv(formData);
        const data = response as { created: number; errors: number; errorDetails?: unknown[] };
        if (data.errors > 0) {
          setResult({
            type: 'success',
            message: t('csv.partialSuccess', { created: data.created, errors: data.errors }),
            details: data.errorDetails,
          });
        } else {
          setResult({ type: 'success', message: t('csv.fullSuccess', { created: data.created }) });
        }
      } catch {
        setResult({ type: 'error', message: t('error') });
      } finally {
        setUploading(false);
      }
    },
    [api, t]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div className="bg-nkz-surface rounded-nkz-md p-6">
      <h2 className="text-nkz-lg font-medium mb-4">{t('tabs.csv')}</h2>

      {/* Result banner */}
      {result && (
        <div
          className={`mb-4 p-3 rounded-nkz-sm text-nkz-sm ${
            result.type === 'success'
              ? 'bg-nkz-success/10 text-nkz-success border border-nkz-success/30'
              : 'bg-nkz-danger/10 text-nkz-danger border border-nkz-danger/30'
          }`}
        >
          {result.message}
          {result.details != null && (
            <details className="mt-2 text-nkz-xs">
              <summary className="cursor-pointer">{t('csv.errorDetails')}</summary>
              <pre className="mt-1 text-nkz-muted whitespace-pre-wrap">
                {JSON.stringify(result.details, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}

      <div
        className={`border-2 border-dashed rounded-nkz-md p-8 text-center transition-colors ${
          uploading ? 'border-nkz-primary/50 bg-nkz-primary/5' : 'border-nkz-border'
        }`}
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
      >
        {uploading ? (
          <p className="text-nkz-muted">{t('csv.uploading')}</p>
        ) : (
          <label className="cursor-pointer">
            <span className="text-nkz-muted">{t('csvDropzone')}</span>
            <input
              type="file"
              accept=".csv"
              className="hidden"
              onChange={handleChange}
            />
          </label>
        )}
        {fileName && !uploading && (
          <p className="text-nkz-xs text-nkz-muted mt-2">{fileName}</p>
        )}
        <p className="text-nkz-xs text-nkz-muted mt-2">{t('csvFormat')}</p>
      </div>
    </div>
  );
}

// ─── History Tab ─────────────────────────────────────────────────────────

function HistoryTab() {
  const { t } = useTranslation('soil');
  const { data: surveys, isLoading: surveysLoading } = useEntities<NgsiLdEntity>('SoilSurvey');
  const { data: samplingPoints, isLoading: pointsLoading } = useEntities<NgsiLdEntity>('SoilSamplingPoint');
  const [expandedSurvey, setExpandedSurvey] = useState<string | null>(null);

  const loading = surveysLoading || pointsLoading;

  if (loading) {
    return (
      <div className="bg-nkz-surface rounded-nkz-md p-6">
        <p className="text-nkz-muted text-nkz-sm">{t('loading')}</p>
      </div>
    );
  }

  const surveyList = surveys || [];
  const pointsList = samplingPoints || [];

  if (surveyList.length === 0 && pointsList.length === 0) {
    return (
      <div className="bg-nkz-surface rounded-nkz-md p-6">
        <h2 className="text-nkz-lg font-medium mb-4">{t('tabs.history')}</h2>
        <div className="text-center py-8">
          <p className="text-nkz-muted text-nkz-sm">{t('history.noData')}</p>
          <p className="text-nkz-xs text-nkz-muted mt-2">{t('history.noDataHint')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Surveys */}
      {surveyList.length > 0 && (
        <div className="bg-nkz-surface rounded-nkz-md p-6">
          <h2 className="text-nkz-lg font-medium mb-4">{t('history.surveys')}</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-nkz-sm">
              <thead>
                <tr className="text-nkz-muted border-b border-nkz-border">
                  <th className="text-left py-2 pr-4">{t('history.type')}</th>
                  <th className="text-left py-2 pr-4">{t('history.date')}</th>
                  <th className="text-left py-2 pr-4">{t('history.points')}</th>
                  <th className="text-left py-2">{t('history.instrumentation')}</th>
                </tr>
              </thead>
              <tbody>
                {surveyList.map((survey) => {
                  const s = survey as Record<string, Record<string, unknown> | undefined>;
                  const surveyType = s.surveyType;
                  const startDate = s.startDate;
                  const pointCount = s.pointCount;
                  const instrumentation = s.instrumentation;
                  const isExpanded = expandedSurvey === survey.id;

                  // Find points for this survey
                  const surveyPoints = pointsList.filter((p) => {
                    const ps = p as Record<string, Record<string, unknown> | undefined>;
                    const refSurvey = ps.refSoilSurvey;
                    return refSurvey?.object === survey.id;
                  });

                  return (
                    <React.Fragment key={survey.id}>
                      <tr
                        className="border-b border-nkz-border/50 cursor-pointer hover:bg-nkz-muted/5"
                        onClick={() => setExpandedSurvey(isExpanded ? null : survey.id)}
                      >
                        <td className="py-2 pr-4">
                          <span className={`px-2 py-0.5 rounded-nkz-sm text-nkz-xs ${
                            surveyType?.value === 'lab' ? 'bg-nkz-primary/10 text-nkz-primary' :
                            surveyType?.value === 'em' ? 'bg-nkz-warning/10 text-nkz-warning' :
                            surveyType?.value === 'nir' ? 'bg-purple-100 text-purple-700' :
                            'bg-nkz-muted/10 text-nkz-muted'
                          }`}>
                            {String(surveyType?.value || '—')}
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-nkz-muted">
                          {typeof startDate?.value === 'string' ? startDate.value.substring(0, 10) : '—'}
                        </td>
                        <td className="py-2 pr-4">{Number(pointCount?.value) || surveyPoints.length || 0}</td>
                        <td className="py-2 text-nkz-muted">{typeof instrumentation?.value === 'string' ? instrumentation.value : '—'}</td>
                      </tr>
                      {isExpanded && surveyPoints.length > 0 && (
                        <tr>
                          <td colSpan={4} className="py-2 px-4 bg-nkz-muted/5">
                            <div className="text-nkz-xs space-y-1">
                              {surveyPoints.map((p) => {
                                const ps = p as Record<string, Record<string, unknown> | undefined>;
                                const loc = ps.location;
                                const coords = (loc?.value as Record<string, unknown>)?.coordinates as number[] | undefined;
                                const samplingDate = ps.samplingDate;
                                const horizons = ps.horizons;
                                const hList = (horizons?.value as Array<Record<string, unknown>>) || [];
                                const topH = hList[0] || {};

                                return (
                                  <div key={p.id} className="flex gap-4 text-nkz-muted">
                                    <span>{coords ? `${coords[1].toFixed(4)}, ${coords[0].toFixed(4)}` : '—'}</span>
                                    <span>{String(samplingDate?.value || '').substring(0, 10) || '—'}</span>
                                    <span>
                                      {topH.sand != null && `S:${topH.sand}% Si:${topH.silt}% C:${topH.clay}%`}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Orphan sampling points (not linked to a survey) */}
      {pointsList.length > 0 && (
        <div className="bg-nkz-surface rounded-nkz-md p-6">
          <h2 className="text-nkz-lg font-medium mb-4">{t('history.points')}</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-nkz-sm">
              <thead>
                <tr className="text-nkz-muted border-b border-nkz-border">
                  <th className="text-left py-2 pr-4">{t('history.coordinates')}</th>
                  <th className="text-left py-2 pr-4">{t('history.date')}</th>
                  <th className="text-left py-2 pr-4">{t('history.depth')}</th>
                  <th className="text-left py-2">{t('history.texture')}</th>
                </tr>
              </thead>
              <tbody>
                {pointsList.map((p) => {
                  const ps = p as Record<string, Record<string, unknown> | undefined>;
                  const loc = ps.location;
                  const coords = (loc?.value as Record<string, unknown>)?.coordinates as number[] | undefined;
                  const samplingDate = ps.samplingDate;
                  const horizons = ps.horizons;
                  const hList = (horizons?.value as Array<Record<string, unknown>>) || [];

                  return (
                    <tr key={p.id} className="border-b border-nkz-border/50">
                      <td className="py-2 pr-4">
                        {coords ? `${coords[1].toFixed(4)}, ${coords[0].toFixed(4)}` : '—'}
                      </td>
                      <td className="py-2 pr-4 text-nkz-muted">
                        {typeof samplingDate?.value === 'string' ? samplingDate.value.substring(0, 10) : '—'}
                      </td>
                      <td className="py-2 pr-4 text-nkz-muted">
                        {hList.length > 0 ? `${hList[0].depthFrom}–${hList[0].depthTo} cm` : '—'}
                      </td>
                      <td className="py-2 text-nkz-muted">
                        {hList[0]?.sand != null
                          ? `${hList[0].sand}/${hList[0].silt}/${hList[0].clay}%`
                          : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
