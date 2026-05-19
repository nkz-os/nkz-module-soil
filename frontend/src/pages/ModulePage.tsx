import React, { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { SlotShellCompact } from '@nekazari/viewer-kit';
import { useSoilApi } from '../hooks/useSoilApi';

type Tab = 'dashboard' | 'manual' | 'csv' | 'history';

export default function ModulePage() {
  const { t } = useTranslation('soil');
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');

  const tabs: { id: Tab; label: string }[] = [
    { id: 'dashboard', label: t('tabs.dashboard') },
    { id: 'manual', label: t('tabs.manual') },
    { id: 'csv', label: t('tabs.csv') },
    { id: 'history', label: t('tabs.history') },
  ];

  return (
    <SlotShellCompact title={t('title')}>
      <div className="max-w-5xl mx-auto p-6 space-y-6">
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

function DashboardTab() {
  const { t } = useTranslation('soil');

  return (
    <div className="bg-nkz-surface rounded-nkz-md p-6">
      <h2 className="text-nkz-lg font-medium mb-2">{t('tabs.dashboard')}</h2>
      <p className="text-nkz-muted text-nkz-sm">{t('dashboardDescription')}</p>
      <p className="text-nkz-sm mt-4 text-nkz-muted">{t('dashboardPlaceholder')}</p>
    </div>
  );
}

function ManualSamplingTab() {
  const { t } = useTranslation('soil');
  const api = useSoilApi();
  const [result, setResult] = useState<string | null>(null);

  const fields = [
    { key: 'lat', label: t('fields.lat') },
    { key: 'lon', label: t('fields.lon') },
    { key: 'depthFrom', label: t('fields.depthFrom') },
    { key: 'depthTo', label: t('fields.depthTo') },
    { key: 'sand', label: t('fields.sand') },
    { key: 'silt', label: t('fields.silt') },
    { key: 'clay', label: t('fields.clay') },
    { key: 'organicCarbon', label: t('fields.organicCarbon') },
    { key: 'ph', label: t('fields.ph') },
    { key: 'bulkDensity', label: t('fields.bulkDensity') },
    { key: 'penetrationResistance', label: t('fields.penetrationResistance') },
  ];

  const [form, setForm] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((f) => [f.key, '']))
  );

  const handleChange = (field: string, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async () => {
    const sand = Number(form.sand) || 0;
    const silt = Number(form.silt) || 0;
    const clay = Number(form.clay) || 0;
    if (sand + silt + clay > 0) {
      const total = sand + silt + clay;
      if (total < 97 || total > 103) {
        setResult(t('validation.textureSum'));
        return;
      }
    }
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
      });
      setResult(t('success'));
      setForm(Object.fromEntries(fields.map((f) => [f.key, ''])));
    } catch {
      setResult(t('error'));
    }
  };

  return (
    <div className="bg-nkz-surface rounded-nkz-md p-6">
      <h2 className="text-nkz-lg font-medium mb-4">{t('tabs.manual')}</h2>
      <div className="grid grid-cols-2 gap-4">
        {fields.map((field) => (
          <div key={field.key}>
            <label className="block text-nkz-xs mb-1">{field.label}</label>
            <input
              type="number"
              value={form[field.key]}
              onChange={(e) => handleChange(field.key, e.target.value)}
              className="w-full border-nkz-border rounded-nkz-sm px-2 py-1 text-nkz-sm"
            />
          </div>
        ))}
      </div>
      <button
        onClick={handleSubmit}
        className="mt-4 px-4 py-2 bg-nkz-primary text-white rounded-nkz-sm text-nkz-sm"
      >
        {t('submit')}
      </button>
      {result && <p className="mt-2 text-nkz-sm">{result}</p>}
    </div>
  );
}

function CsvUploadTab() {
  const { t } = useTranslation('soil');
  const api = useSoilApi();
  const [result, setResult] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setFileName(file.name);
      try {
        const formData = new FormData();
        formData.append('file', file);
        await api.uploadCsv(formData);
        setResult(t('success'));
      } catch {
        setResult(t('error'));
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
      <div
        className="border-2 border-dashed border-nkz-border rounded-nkz-md p-8 text-center"
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
      >
        <label className="cursor-pointer">
          <span className="text-nkz-muted">{t('csvDropzone')}</span>
          <input
            type="file"
            accept=".csv"
            className="hidden"
            onChange={handleChange}
          />
        </label>
        {fileName && (
          <p className="text-nkz-xs text-nkz-muted mt-2">{fileName}</p>
        )}
        <p className="text-nkz-xs text-nkz-muted mt-2">{t('csvFormat')}</p>
      </div>
      {result && <p className="mt-2 text-nkz-sm">{result}</p>}
    </div>
  );
}

function HistoryTab() {
  const { t } = useTranslation('soil');

  return (
    <div className="bg-nkz-surface rounded-nkz-md p-6">
      <h2 className="text-nkz-lg font-medium mb-4">{t('tabs.history')}</h2>
      <p className="text-nkz-muted text-nkz-sm">{t('historyPlaceholder')}</p>
    </div>
  );
}
