/**
 * WaterBudgetGauge — animated water tank gauge for soil available water.
 *
 * Shows a vertical tank with water level, field capacity / wilting point lines,
 * AWC remaining percentage with color coding, 7-day forecast table,
 * and irrigation recommendation.
 */
import React from 'react';
import { useI18n } from '@nekazari/module-kit';
import { ThermometerSun, Umbrella, AlertTriangle, CheckCircle2 } from 'lucide-react';

export interface WaterBudgetData {
  fieldCapacity: number;
  wiltingPoint: number;
  awc: number;
  currentMoisture: number;
  awcRemainingPct: number;
  deficitMm: number;
  forecast: Array<{ day: string; et0: number; precip: number; deficitAfter: number }>;
  recommendation: { shouldIrrigate: boolean; amountMm?: number; suggestedDay?: string; reason?: string } | null;
  lastComputed: string;
}

interface WaterBudgetGaugeProps {
  data: WaterBudgetData;
  className?: string;
}

export const WaterBudgetGauge: React.FC<WaterBudgetGaugeProps> = ({ data, className }) => {
  const { t } = useI18n();
  const { fieldCapacity, wiltingPoint, currentMoisture, awcRemainingPct, deficitMm, forecast, recommendation, lastComputed } = data;

  const tankRange = fieldCapacity - wiltingPoint;
  const waterLevel = tankRange > 0 ? ((currentMoisture - wiltingPoint) / tankRange) * 100 : 0;
  const clampedLevel = Math.max(0, Math.min(100, waterLevel));

  const getColor = (pct: number) => {
    if (pct >= 50) return 'text-nkz-green-600 bg-nkz-green-500';
    if (pct >= 25) return 'text-yellow-600 bg-yellow-500';
    return 'text-red-600 bg-red-500';
  };

  const color = getColor(awcRemainingPct);

  return (
    <div className={`space-y-3 ${className ?? ''}`}>
      {/* Tank Gauge */}
      <div className="flex items-center gap-4">
        <div className="relative w-16 h-36 bg-gray-100 rounded-lg border-2 border-gray-300 overflow-hidden">
          <div
            className={`absolute bottom-0 left-0 right-0 transition-all duration-700 ease-in-out ${color.split(' ')[1]}`}
            style={{ height: `${clampedLevel}%` }}
          />
          <div className="absolute top-0 left-0 right-0 border-t-2 border-dashed border-blue-500 text-[8px] text-blue-600 pl-1">
            CC
          </div>
          <div className="absolute bottom-0 left-0 right-0 border-t-2 border-dashed border-red-400 text-[8px] text-red-600 pl-1" style={{ bottom: '0%' }}>
            PMP
          </div>
        </div>

        <div className="flex-1 space-y-1 text-xs">
          <div className="flex justify-between">
            <span className="text-gray-500">{t('waterBudget.awc')}</span>
            <span className="font-medium">{awcRemainingPct != null ? `${Math.round(awcRemainingPct)}%` : '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">{t('waterBudget.deficit')}</span>
            <span className="font-medium">{deficitMm != null ? `${deficitMm} mm` : '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">{t('waterBudget.fieldCapacity')}</span>
            <span className="font-medium">{fieldCapacity != null ? `${(fieldCapacity * 100).toFixed(0)}%` : '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">{t('waterBudget.wiltingPoint')}</span>
            <span className="font-medium">{wiltingPoint != null ? `${(wiltingPoint * 100).toFixed(0)}%` : '—'}</span>
          </div>
        </div>
      </div>

      {/* Recommendation */}
      {recommendation && (
        <div className={`rounded-lg p-2 text-xs flex items-start gap-2 ${
          recommendation.shouldIrrigate ? 'bg-yellow-50 text-yellow-700 border border-yellow-200' : 'bg-nkz-green-50 text-nkz-green-700 border border-nkz-green-100'
        }`}>
          {recommendation.shouldIrrigate ? <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" /> : <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0" />}
          <div>
            {recommendation.shouldIrrigate ? (
              <>
                <p className="font-medium">{t('waterBudget.shouldIrrigate')}</p>
                <p>{t('waterBudget.amount')}: {recommendation.amountMm} mm {recommendation.suggestedDay ? `· ${t('waterBudget.suggestedDay')}: ${recommendation.suggestedDay}` : ''}</p>
                {recommendation.reason && <p className="text-[10px] mt-0.5 opacity-75">{recommendation.reason}</p>}
              </>
            ) : (
              <p className="font-medium">{t('waterBudget.noIrrigation')}</p>
            )}
          </div>
        </div>
      )}

      {/* 7-day Forecast */}
      {forecast.length > 0 && (
        <div>
          <p className="text-xs font-medium text-gray-600 mb-1 flex items-center gap-1">
            <ThermometerSun className="w-3 h-3" />
            {t('waterBudget.forecast')}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-gray-400 border-b border-gray-100">
                  <th className="text-left py-1 pr-2">{t('date.started')}</th>
                  <th className="text-right py-1 px-1">ET0</th>
                  <th className="text-right py-1 px-1"><Umbrella className="w-3 h-3 inline" /></th>
                  <th className="text-right py-1 pl-2">{t('waterBudget.deficit')}</th>
                </tr>
              </thead>
              <tbody>
                {forecast.map((day) => (
                  <tr key={day.day} className="border-b border-gray-50">
                    <td className="py-1 pr-2 text-gray-600">{day.day.slice(5)}</td>
                    <td className="text-right py-1 px-1">{day.et0}mm</td>
                    <td className="text-right py-1 px-1">{day.precip}mm</td>
                    <td className={`text-right py-1 pl-2 font-mono ${day.deficitAfter > deficitMm ? 'text-yellow-600' : 'text-gray-600'}`}>
                      {day.deficitAfter.toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {lastComputed && (
        <p className="text-[10px] text-gray-400 text-right">
          {t('date.lastEvaluation')}: {new Date(lastComputed).toLocaleString()}
        </p>
      )}
    </div>
  );
};

export default WaterBudgetGauge;
