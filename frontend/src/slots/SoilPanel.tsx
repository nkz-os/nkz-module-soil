import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useSoilApi } from '../hooks/useSoilApi';

interface ActiveLayer {
  id: string;
  label: string;
  opacity: number;
}

export function SoilPanel({ entityId }: { entityId?: string }) {
  const { t } = useTranslation('soil');
  const api = useSoilApi();
  const [summary, setSummary] = useState<Record<string, any> | null>(null);
  const [activeLayers, setActiveLayers] = useState<ActiveLayer[]>([]);
  const [selectedHorizon, setSelectedHorizon] = useState('0-30');

  useEffect(() => {
    if (entityId) {
      api.getSummary(entityId).then(setSummary).catch(() => setSummary(null));
    }
  }, [entityId]);

  if (!summary) {
    return (
      <div className="p-3">
        <h3 className="text-nkz-sm font-medium">{t('title')}</h3>
        <p className="text-nkz-muted text-nkz-xs mt-1">{t('summary')}</p>
      </div>
    );
  }

  const horizon = summary.horizons?.[0];

  return (
    <div className="p-3 space-y-3">
      <h3 className="text-nkz-sm font-medium">{t('title')}</h3>

      <div className="text-nkz-xs text-nkz-muted">
        {t('source')}: {summary.dataSource}
      </div>

      <div className="flex items-center gap-2">
        <label className="text-nkz-xs">{t('horizon')}:</label>
        <select
          value={selectedHorizon}
          onChange={(e) => setSelectedHorizon(e.target.value)}
          className="text-nkz-xs border-nkz-border rounded-nkz-sm"
        >
          <option value="0-5">0-5 cm</option>
          <option value="5-15">5-15 cm</option>
          <option value="15-30">15-30 cm</option>
          <option value="30-60">30-60 cm</option>
          <option value="60-100">60-100 cm</option>
        </select>
      </div>

      {horizon && (
        <div className="text-nkz-xs space-y-1">
          <div className="flex justify-between">
            <span>{t('texture')}:</span>
            <span className="font-medium">
              {horizon.sand != null ? `${horizon.sand}% / ${horizon.silt}% / ${horizon.clay}%` : '—'}
            </span>
          </div>
          {horizon.hydrologicGroup && (
            <div className="flex justify-between">
              <span>{t('hydrologicGroup')}:</span>
              <span className="font-medium">{horizon.hydrologicGroup}</span>
            </div>
          )}
          {horizon.ksatSaturated != null && (
            <div className="flex justify-between">
              <span>{t('ksat')}:</span>
              <span className="font-medium">{horizon.ksatSaturated} mm/h</span>
            </div>
          )}
          {summary.relativeCompaction?.[0] && (
            <div className="flex justify-between">
              <span>{t('compaction')}:</span>
              <span className="font-medium">
                {summary.relativeCompaction[0].classification} ({summary.relativeCompaction[0].value}%)
              </span>
            </div>
          )}
        </div>
      )}

      {activeLayers.length > 0 && (
        <div className="border-t border-nkz-border pt-2">
          <div className="text-nkz-xs font-medium mb-1">Active Layers</div>
          {activeLayers.map((layer) => (
            <div key={layer.id} className="flex items-center gap-2 text-nkz-xs mb-1">
              <input type="checkbox" checked readOnly className="w-3 h-3" />
              <span className="flex-1">{layer.label}</span>
              <input
                type="range"
                min="0"
                max="100"
                value={layer.opacity}
                onChange={() => {}}
                className="w-12 h-1"
              />
            </div>
          ))}
        </div>
      )}

      <a
        href={`/module/soil?parcel=${entityId}`}
        className="text-nkz-xs text-nkz-primary hover:underline block"
      >
        {t('viewDetails')} →
      </a>
    </div>
  );
}
