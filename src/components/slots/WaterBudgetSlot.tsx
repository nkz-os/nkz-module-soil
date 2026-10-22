/**
 * WaterBudgetSlot — context-panel slot widget for AgriParcel.
 *
 * Shows the water budget gauge when a parcel is selected in the viewer.
 */
import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useViewer } from '@nekazari/sdk';
import { Droplets, Loader2, AlertCircle } from 'lucide-react';
import { useSoilApi } from '../../hooks/useSoilApi';
import { WaterBudgetGauge, WaterBudgetData } from '../WaterBudgetGauge';

interface WaterBudgetSlotProps {
  className?: string;
}

export const WaterBudgetSlot: React.FC<WaterBudgetSlotProps> = ({ className }) => {
  const { t } = useTranslation('soil');
  const api = useSoilApi();
  const { selectedEntityId, selectedEntityType } = useViewer();
  const [data, setData] = useState<WaterBudgetData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedEntityId || selectedEntityType !== 'AgriParcel') {
      setData(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    api
      .getWaterBudget(selectedEntityId)
      .then((result) => {
        if (cancelled) return;
        setData(result as unknown as WaterBudgetData);
        setLoading(false);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [selectedEntityId, selectedEntityType, api]);

  if (!selectedEntityId || selectedEntityType !== 'AgriParcel') return null;

  return (
    <div className={`p-4 space-y-3 ${className ?? ''}`}>
      <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
        <Droplets className="w-4 h-4 text-blue-500" />
        {t('waterBudget.title')}
      </h3>

      {loading && (
        <div className="flex items-center justify-center py-6 text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      )}

      {error && (
        <div className="text-center text-gray-400 text-xs py-4">
          <AlertCircle className="w-5 h-5 mx-auto mb-1 opacity-40" />
          <p>{error}</p>
        </div>
      )}

      {data && <WaterBudgetGauge data={data} />}
    </div>
  );
};

export default WaterBudgetSlot;
