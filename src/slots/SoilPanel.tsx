import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { SlotShell } from '@nekazari/viewer-kit';
import { useSoilApi } from '../hooks/useSoilApi';
import { ModuleAttribution } from '../components/ModuleAttribution';
import { PenetrometerForm } from '../components/PenetrometerForm';
import { ngsiValue, soilHorizons } from '../lib/ngsiValue';

export function SoilPanel({ entityId }: { entityId?: string }) {
  const { t } = useTranslation('soil');
  const api = useSoilApi();
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [selectedHorizon, setSelectedHorizon] = useState('0-30');

  useEffect(() => {
    if (entityId) {
      api.getSummary(entityId)
        .then((data: unknown) => setSummary(data as Record<string, unknown> | null))
        .catch(() => setSummary(null));
    }
  }, [entityId, api]);

  if (!summary) {
    return (
      <SlotShell moduleId="soil" title={t('title')}>
        <p className="text-nkz-muted text-nkz-xs">{t('summary')}</p>
      </SlotShell>
    );
  }

  const horizons = soilHorizons(summary) as Array<Record<string, unknown>>;
  const horizon = horizons.find(
    (h) => h.depthFrom === parseInt(selectedHorizon.split('-')[0]) &&
           h.depthTo === parseInt(selectedHorizon.split('-')[1])
  ) || horizons[0];

  return (
    <SlotShell moduleId="soil" title={t('title')}>
      <div className="space-y-3">
        <div className="text-nkz-xs text-nkz-muted">
          {t('source')}: {String(ngsiValue(summary.dataSource) ?? '')}
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
                {horizon.sand != null
                  ? `${horizon.sand}% / ${horizon.silt}% / ${horizon.clay}%`
                  : '\u2014'}
              </span>
            </div>
            {horizon.usdaTextureClass != null && (
              <div className="flex justify-between">
                <span>{t('textureClass', 'Texture class')}:</span>
                <span className="font-medium">{String(horizon.usdaTextureClass)}</span>
              </div>
            )}
            {horizon.hydrologicGroup != null && (
              <div className="flex justify-between">
                <span>{t('hydrologicGroup')}:</span>
                <span className="font-medium">{String(horizon.hydrologicGroup)}</span>
              </div>
            )}
            {horizon.ksatSaturated != null && (
              <div className="flex justify-between">
                <span>{t('ksat')}:</span>
                <span className="font-medium">{String(horizon.ksatSaturated)} mm/h</span>
              </div>
            )}
            {(ngsiValue<Array<Record<string, unknown>>>(summary.relativeCompaction) ?? [])[0] && (
              <div className="flex justify-between">
                <span>{t('compaction')}:</span>
                <span className="font-medium">
                  {String((ngsiValue<Array<Record<string, unknown>>>(summary.relativeCompaction) ?? [])[0].classification)}{' '}
                  ({String((ngsiValue<Array<Record<string, unknown>>>(summary.relativeCompaction) ?? [])[0].value)}%)
                </span>
              </div>
            )}
          </div>
        )}

        <Link
          to={`/module/soil?parcel=${entityId}`}
          className="text-nkz-xs text-nkz-primary hover:underline block"
        >
          {t('viewDetails')} \u2192
        </Link>

        <hr className="border-nkz-border" />
        <PenetrometerForm parcelId={entityId || ''} />
        <ModuleAttribution />
      </div>
    </SlotShell>
  );
}
