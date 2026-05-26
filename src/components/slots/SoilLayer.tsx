import { useEffect, useRef } from 'react';
import { useViewerOptional } from '@nekazari/sdk';
import { useSoilLayerContext } from '../../services/soilLayerContext';
import { useSoilApi } from '../../hooks/useSoilApi';
import { soilLayerColor } from '../../lib/soilLayerColor';

export function SoilLayer({ entityId }: { entityId?: string }) {
  const viewerCtx = useViewerOptional();
  const viewer = (viewerCtx as any)?.cesiumViewer;
  const api = useSoilApi();
  const { attribute, visible, opacity, scope } = useSoilLayerContext();
  const dsRef = useRef<any>(null);

  useEffect(() => {
    if (!viewer) return;
    const Cesium = (window as any).Cesium;
    if (!Cesium) return;

    if (dsRef.current) {
      try { viewer.dataSources.remove(dsRef.current, true); } catch { /* destroyed */ }
      dsRef.current = null;
    }
    if (!visible) return;

    const parcel = scope === 'selected' && entityId
      ? entityId.split(':').pop() : undefined;
    if (scope === 'selected' && !parcel) return;

    let cancelled = false;
    api.getParcelsGeoJson(attribute, scope, parcel)
      .then((fc) => {
        if (cancelled || viewer.isDestroyed()) return;
        return Cesium.GeoJsonDataSource.load(fc, { clampToGround: true });
      })
      .then((ds: any) => {
        if (!ds || cancelled || viewer.isDestroyed()) return;
        for (const ent of ds.entities.values) {
          const v = ent.properties?.value?.getValue?.();
          const hex = soilLayerColor(attribute, v ?? null);
          if (ent.polygon) {
            ent.polygon.material = Cesium.Color.fromCssColorString(hex).withAlpha(opacity);
            ent.polygon.outline = true;
            ent.polygon.outlineColor = Cesium.Color.BLACK.withAlpha(0.4);
          }
        }
        viewer.dataSources.add(ds);
        dsRef.current = ds;
      })
      .catch(() => { /* parcel may have no soil data */ });

    return () => { cancelled = true; };
  }, [viewer, attribute, visible, opacity, scope, entityId, api]);

  return null;
}

export default SoilLayer;
