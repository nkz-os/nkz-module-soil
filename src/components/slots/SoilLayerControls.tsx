import React from 'react';
import { useTranslation } from 'react-i18next';
import { useSoilLayerContext, LayerScope } from '../../services/soilLayerContext';
import { ModuleAttribution } from '../ModuleAttribution';
import { LAYER_ATTRIBUTES, legendFor } from '../../lib/soilLayerColor';

/**
 * Soil layer *configuration* (attribute, scope, legend). Visibility and opacity
 * are controlled from the host's unified Layers menu via the LayerRegistry.
 */
export function SoilLayerControls() {
  const { t } = useTranslation('soil');
  const { attribute, setAttribute, scope, setScope } = useSoilLayerContext();

  const legend = legendFor(attribute);

  return (
    <div className="space-y-2 text-nkz-xs border border-nkz-border/50 rounded-nkz-sm p-2">
      <span className="font-medium">{t('layer.title', 'Soil')}</span>
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

      {/* Legend — colors are data encodings (not design-token colors), so inline style is required. */}
      {legend.kind === 'categorical' ? (
        <div className="grid grid-cols-2 gap-x-2 gap-y-1 pt-1">
          {legend.entries.map((e) => (
            <div key={e.value} className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-nkz-sm border border-nkz-border"
                    style={{ backgroundColor: e.color }} />
              <span className="text-nkz-muted truncate">{e.value}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-1 pt-1">
          <div className="h-2 w-full rounded-nkz-sm"
               style={{ background: `linear-gradient(to right, ${legend.colors.join(', ')})` }} />
          <div className="flex justify-between text-nkz-muted">
            <span>{legend.range[0]}{legend.unit ? ` ${legend.unit}` : ''}</span>
            <span>{legend.range[1]}{legend.unit ? ` ${legend.unit}` : ''}</span>
          </div>
        </div>
      )}

      <ModuleAttribution />
    </div>
  );
}

export default SoilLayerControls;
