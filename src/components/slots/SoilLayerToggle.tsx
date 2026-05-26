import React from 'react';
import { useTranslation } from 'react-i18next';
import { useSoilLayerContext, LayerScope } from '../../services/soilLayerContext';
import { LAYER_ATTRIBUTES } from '../../lib/soilLayerColor';

export function SoilLayerToggle() {
  const { t } = useTranslation('soil');
  const { attribute, setAttribute, visible, setVisible, opacity, setOpacity, scope, setScope } =
    useSoilLayerContext();
  return (
    <div className="space-y-2 text-nkz-xs">
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} />
        <span className="font-medium">{t('layer.title', 'Soil')}</span>
      </label>
      {visible && (
        <div className="space-y-2 pl-5">
          <select value={attribute} onChange={(e) => setAttribute(e.target.value)}
                  className="text-nkz-xs border-nkz-border rounded-nkz-sm w-full">
            {LAYER_ATTRIBUTES.map(a => (
              <option key={a.id} value={a.id}>{t(`layer.attr.${a.id}`, a.id)}</option>
            ))}
          </select>
          <div className="flex gap-2">
            {(['selected', 'all'] as LayerScope[]).map(s => (
              <button key={s} onClick={() => setScope(s)}
                className={`px-2 py-1 rounded-nkz-sm border ${scope === s ? 'border-nkz-primary text-nkz-primary' : 'border-nkz-border text-nkz-muted'}`}>
                {t(`layer.scope.${s}`, s)}
              </button>
            ))}
          </div>
          <input type="range" min={0.2} max={1} step={0.1} value={opacity}
                 onChange={(e) => setOpacity(Number(e.target.value))} className="w-full" />
        </div>
      )}
    </div>
  );
}

export default SoilLayerToggle;
