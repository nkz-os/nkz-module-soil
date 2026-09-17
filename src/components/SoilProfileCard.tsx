import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useViewer } from '@nekazari/sdk';
import { useSoilApi } from '../hooks/useSoilApi';
import { soilLayerColor } from '../lib/soilLayerColor';

interface HorizonData {
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
  compactionSusceptibility?: {
    score: number;
    class: string;
    texturalScore: number;
    modifiersApplied: string[];
    indicativeElevatedBd: boolean;
  };
}

interface SoilProfileCardProps {
  entityId?: string;
  maxDepth?: number;
}

/**
 * Vertical soil profile card — renders horizons as stacked horizontal bars
 * coloured by USDA texture class, with key hydraulic properties per horizon.
 *
 * Designed for the parcel viewer context-panel slot.  Shows "No soil data"
 * placeholder when the parcel has no AgriSoilExtended entity yet.
 */
export function SoilProfileCard({ entityId: entityIdProp, maxDepth = 100 }: SoilProfileCardProps) {
  const { t } = useTranslation('soil');
  const api = useSoilApi();
  // ModulePage passes entityId explicitly; the viewer's context-panel slot
  // never passes flat props at all (only additionalProps={{ entityData }}),
  // so fall back to the viewer's own selection in that case.
  const { selectedEntityId } = useViewer();
  const entityId = entityIdProp ?? selectedEntityId;
  const [horizons, setHorizons] = useState<HorizonData[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!entityId) {
      setHorizons(null);
      return;
    }
    let cancelled = false;
    api
      .getHorizons(entityId, `0-${maxDepth}`)
      .then((data: unknown) => {
        if (cancelled) return;
        const d = data as { horizons: HorizonData[] };
        if (d.horizons && d.horizons.length > 0) {
          setHorizons(d.horizons);
          setError(false);
        } else {
          setHorizons(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHorizons(null);
          setError(true);
        }
      });
    return () => { cancelled = true; };
  }, [entityId, maxDepth, api]);

  if (error) {
    return (
      <div className="p-3 text-nkz-xs text-nkz-muted italic">
        {t('profile.error', 'Could not load soil profile')}
      </div>
    );
  }

  if (!horizons || horizons.length === 0) {
    return (
      <div className="p-3 text-nkz-xs text-nkz-muted">
        {t('profile.noData', 'No soil profile data for this parcel')}
      </div>
    );
  }

  const totalDepth = Math.max(maxDepth, horizons[horizons.length - 1]?.depthTo ?? 100);
  const barHeight = 180; // px for the full profile
  const depthLabelInterval = 20; // label every 20 cm

  return (
    <div className="space-y-2 text-nkz-xs">
      <h4 className="font-medium text-nkz-sm">{t('profile.title', 'Soil Profile')}</h4>

      {/* Horizons stacked bar */}
      <div className="flex gap-2">
        {/* Depth scale */}
        <div className="relative flex flex-col justify-between text-nkz-muted pr-1" style={{ height: barHeight }}>
          {Array.from({ length: Math.floor(totalDepth / depthLabelInterval) + 1 }, (_, i) => {
            const depth = i * depthLabelInterval;
            const topPct = (depth / totalDepth) * 100;
            return (
              <div key={depth} className="text-right text-[10px] leading-none absolute" style={{ top: `${100 - topPct}%`, right: 4, transform: depth === 0 ? 'translateY(0)' : depth === totalDepth ? 'translateY(-100%)' : 'translateY(-50%)' }}>
                {depth}
              </div>
            );
          })}
          <span className="text-[10px] text-nkz-muted mt-auto">cm</span>
        </div>

        {/* Bars */}
        <div className="flex-1 relative" style={{ height: barHeight }}>
          {horizons.map((h) => {
            const depthPct = ((h.depthTo - h.depthFrom) / totalDepth) * 100;
            const topPct = 100 - (h.depthTo / totalDepth) * 100;
            const texClass = h.usdaTextureClass || 'loam';
            const color = soilLayerColor('usdaTextureClass', texClass);

            return (
              <div
                key={`${h.depthFrom}-${h.depthTo}`}
                className="absolute left-0 right-0 rounded-nkz-sm border border-nkz-border/40 flex items-center justify-center overflow-hidden"
                style={{
                  top: `${topPct}%`,
                  height: `${Math.max(depthPct, 4)}%`,
                  backgroundColor: color,
                  opacity: 0.75,
                }}
                title={`${h.depthFrom}–${h.depthTo} cm: ${texClass}`}
              >
                <span className="text-[9px] font-medium truncate px-1 mix-blend-difference text-white">
                  {texClass}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Horizon details table */}
      <div className="overflow-x-auto">
        <table className="w-full text-nkz-xs border-collapse">
          <thead>
            <tr className="text-nkz-muted border-b border-nkz-border">
              <th className="text-left py-1 pr-2">{t('profile.depth', 'Depth')}</th>
              <th className="text-left py-1 pr-2">{t('profile.texture', 'Texture')}</th>
              <th className="text-right py-1 pr-2">{t('profile.fc', 'FC')}</th>
              <th className="text-right py-1 pr-2">{t('profile.wp', 'WP')}</th>
              <th className="text-right py-1 pr-2">{t('profile.ksat', 'Ksat')}</th>
              <th className="text-right py-1 pr-2">{t('fields.ph', 'pH')}</th>
              <th className="text-center py-1">{t('profile.group', 'SCS')}</th>
            </tr>
          </thead>
          <tbody>
            {horizons.map((h) => (
              <tr key={`${h.depthFrom}-${h.depthTo}`} className="border-b border-nkz-border/30">
                <td className="py-1 pr-2">{h.depthFrom}–{h.depthTo}</td>
                <td className="py-1 pr-2">
                  <span className="inline-flex items-center gap-1">
                    <span
                      className="inline-block w-2.5 h-2.5 rounded-nkz-sm border border-nkz-border"
                      style={{ backgroundColor: soilLayerColor('usdaTextureClass', h.usdaTextureClass || 'loam') }}
                    />
                    {h.usdaTextureClass || '—'}
                  </span>
                </td>
                <td className="py-1 pr-2 text-right">
                  {h.fieldCapacity != null ? (h.fieldCapacity * 100).toFixed(1) : '—'}%
                </td>
                <td className="py-1 pr-2 text-right">
                  {h.wiltingPoint != null ? (h.wiltingPoint * 100).toFixed(1) : '—'}%
                </td>
                <td className="py-1 pr-2 text-right">
                  {h.ksatSaturated != null ? `${h.ksatSaturated.toFixed(1)} mm/h` : '—'}
                </td>
                <td className="py-1 pr-2 text-right">
                  {h.ph != null ? h.ph.toFixed(1) : '—'}
                </td>
                <td className="py-1 text-center">
                  {h.hydrologicGroup ? (
                    <span className={`px-1.5 py-0.5 rounded-nkz-sm text-[10px] font-medium ${
                      h.hydrologicGroup === 'A' ? 'bg-green-100 text-green-800' :
                      h.hydrologicGroup === 'B' ? 'bg-blue-100 text-blue-800' :
                      h.hydrologicGroup === 'C' ? 'bg-orange-100 text-orange-800' :
                      'bg-red-100 text-red-800'
                    }`}>{h.hydrologicGroup}</span>
                  ) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Sand/Silt/Clay composition bars per horizon */}
      <div className="space-y-1 pt-1">
        {horizons.map((h) => {
          const sand = h.sand ?? 0;
          const silt = h.silt ?? 0;
          const clay = h.clay ?? 0;
          const total = sand + silt + clay;
          if (total < 1) return null;
          return (
            <div key={`comp-${h.depthFrom}-${h.depthTo}`} className="flex items-center gap-2">
              <span className="w-10 text-nkz-muted text-[10px]">{h.depthFrom}–{h.depthTo}</span>
              <div className="flex-1 h-3 rounded-nkz-sm overflow-hidden flex">
                <div style={{ width: `${(sand / total) * 100}%` }} className="bg-yellow-500" title={`Sand ${sand}%`} />
                <div style={{ width: `${(silt / total) * 100}%` }} className="bg-green-600" title={`Silt ${silt}%`} />
                <div style={{ width: `${(clay / total) * 100}%` }} className="bg-red-700" title={`Clay ${clay}%`} />
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex gap-3 text-[10px] text-nkz-muted">
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 bg-yellow-500 rounded-nkz-sm" /> {t('profile.sand', 'Sand')}</span>
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 bg-green-600 rounded-nkz-sm" /> {t('profile.silt', 'Silt')}</span>
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 bg-red-700 rounded-nkz-sm" /> {t('profile.clay', 'Clay')}</span>
      </div>

      {/* Compaction susceptibility per horizon (if available) */}
      {horizons.some((h) => h.compactionSusceptibility) && (
        <div className="pt-2 border-t border-nkz-border">
          <h5 className="font-medium text-nkz-xs mb-1">{t('profile.compactionRisk', 'Compaction Susceptibility')}</h5>
          {horizons.filter((h) => h.compactionSusceptibility).map((h) => {
            const cs = h.compactionSusceptibility!;
            const scoreColor =
              cs.score < 25 ? 'text-green-600' :
              cs.score < 50 ? 'text-yellow-600' :
              cs.score < 75 ? 'text-orange-600' : 'text-red-600';
            return (
              <div key={`cs-${h.depthFrom}-${h.depthTo}`} className="flex items-center justify-between text-nkz-xs py-0.5">
                <span className="text-nkz-muted">{h.depthFrom}–{h.depthTo} cm</span>
                <span className={`font-medium ${scoreColor}`}>
                  {cs.class} ({cs.score})
                </span>
                {cs.indicativeElevatedBd && (
                  <span className="text-nkz-warning text-[10px]" title={t('profile.elevatedBd', 'Elevated bulk density')}>⚠ BD</span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default SoilProfileCard;
