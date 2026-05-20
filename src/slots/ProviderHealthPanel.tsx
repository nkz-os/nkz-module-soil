import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { SlotShell } from '@nekazari/viewer-kit';
import { useSoilApi } from '../hooks/useSoilApi';

interface ProviderMetric {
  provider: string;
  latency: { min: number; max: number; avg: number; p95: number; count: number };
  error_rate: number;
  cache: { hits: number; misses: number; hit_rate: number };
  total_fetches: number;
  total_errors: number;
}

interface AttributionEntry {
  provider: string;
  text: string;
}

const ATTRIBUTION_MAP: Record<string, AttributionEntry> = {
  idena: { provider: 'idena', text: 'Servicio proporcionado por el Gobierno de Navarra (CC BY 4.0 ES)' },
  igme: { provider: 'igme', text: 'Instituto Geológico y Minero de España (IGME)' },
  bgs: { provider: 'bgs', text: 'UKRI / British Geological Survey and Cranfield University LandIS Portal' },
  soilgrids: { provider: 'soilgrids', text: 'ISRIC World Soil Information, SoilGrids v2.0' },
  lucas: { provider: 'lucas', text: 'European Commission, Joint Research Centre (JRC), LUCAS Topsoil Survey' },
  eu_soil_hydro: { provider: 'eu_soil_hydro', text: 'JRC ESDAC EU-SoilHydroGrids v1.0 (non-commercial use only)' },
};

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation('soil');
  const colorMap: Record<string, string> = {
    ok: 'bg-nkz-success/20 text-nkz-success',
    down: 'bg-nkz-danger/20 text-nkz-danger',
    degraded: 'bg-nkz-warning/20 text-nkz-warning',
  };
  const labelMap: Record<string, string> = {
    ok: t('health.ok'),
    down: t('health.down'),
    degraded: t('health.degraded'),
  };
  return (
    <span className={`text-nkz-xs px-2 py-0.5 rounded-nkz-sm ${colorMap[status] || 'bg-nkz-muted/20 text-nkz-muted'}`}>
      {labelMap[status] || status}
    </span>
  );
}

export function ProviderHealthPanel() {
  const { t } = useTranslation('soil');
  const api = useSoilApi();
  const [metrics, setMetrics] = useState<ProviderMetric[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getMetrics()
      .then((data) => {
        setMetrics(data.providers || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [api]);

  if (loading) {
    return (
      <SlotShell moduleId="soil" title={t('health.title')}>
        <p className="text-nkz-xs text-nkz-muted">Loading...</p>
      </SlotShell>
    );
  }

  if (metrics.length === 0) {
    return (
      <SlotShell moduleId="soil" title={t('health.title')}>
        <p className="text-nkz-xs text-nkz-muted">{t('dashboardPlaceholder')}</p>
      </SlotShell>
    );
  }

  return (
    <SlotShell moduleId="soil" title={t('health.title')}>
      <div className="space-y-3">
        <div className="overflow-x-auto">
          <table className="w-full text-nkz-xs">
            <thead>
              <tr className="text-nkz-muted border-b border-nkz-border">
                <th className="text-left py-1 pr-2">{t('health.provider')}</th>
                <th className="text-left py-1 pr-2">{t('health.status')}</th>
                <th className="text-right py-1 pr-2">{t('health.latency')}</th>
                <th className="text-right py-1 pr-2">{t('health.errorRate')}</th>
                <th className="text-right py-1">{t('health.cacheHitRate')}</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map((m) => (
                <tr key={m.provider} className="border-b border-nkz-border/50">
                  <td className="py-1 pr-2 font-medium">{m.provider}</td>
                  <td className="py-1 pr-2">
                    <StatusBadge status={m.error_rate > 0.5 ? 'down' : m.error_rate > 0.1 ? 'degraded' : 'ok'} />
                  </td>
                  <td className="py-1 pr-2 text-right">
                    {m.latency.count > 0 ? `${m.latency.avg.toFixed(0)} ms` : '\u2014'}
                  </td>
                  <td className="py-1 pr-2 text-right">
                    {(m.error_rate * 100).toFixed(1)}%
                  </td>
                  <td className="py-1 text-right">
                    {(m.cache.hit_rate * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="text-nkz-xs text-nkz-muted space-y-1 pt-2 border-t border-nkz-border">
          <div className="font-medium">{t('health.attribution')}:</div>
          {Object.values(ATTRIBUTION_MAP).map((entry) => (
            <div key={entry.provider} className="text-nkz-2xs opacity-75">
              {entry.text}
            </div>
          ))}
        </div>
      </div>
    </SlotShell>
  );
}
