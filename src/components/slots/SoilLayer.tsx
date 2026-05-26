import { useEffect, useRef } from 'react';
import { useViewerOptional } from '@nekazari/sdk';
import { useSoilLayerContext } from '../../services/soilLayerContext';
import { useSoilApi } from '../../hooks/useSoilApi';
import { soilLayerColor } from '../../lib/soilLayerColor';

/**
 * map-layer slot: renders nothing; imperatively manages a Cesium GeoJsonDataSource.
 * The selected entity comes from the host viewer context (useViewerOptional().selectedEntityId)
 * — the host does NOT pass it as a prop to map-layer slots.
 */
export function SoilLayer() {
  const viewerCtx = useViewerOptional();
  const viewer = (viewerCtx as any)?.cesiumViewer;
  const selectedEntityId = (viewerCtx as any)?.selectedEntityId as string | null | undefined;
  const api = useSoilApi();
  const { attribute, visible, opacity, scope, setStatus } = useSoilLayerContext();
  const dsRef = useRef<any>(null);

  useEffect(() => {
    if (!viewer) return;
    const Cesium = (window as any).Cesium;
    if (!Cesium) return;

    if (dsRef.current) {
      try { viewer.dataSources.remove(dsRef.current, true); } catch { /* destroyed */ }
      dsRef.current = null;
    }
    if (!visible) { setStatus('idle'); return; }

    const parcel = scope === 'selected' && selectedEntityId
      ? selectedEntityId.split(':').pop() : undefined;
    if (scope === 'selected' && !parcel) { setStatus('noSelection'); return; }

    let cancelled = false;
    setStatus('loading');
    api.getParcelsGeoJson(attribute, scope, parcel)
      .then((fc) => {
        if (cancelled || viewer.isDestroyed()) return null;
        const count = (fc as any)?.features?.length ?? 0;
        if (count === 0) { setStatus('empty'); return null; }
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
        setStatus('ready');
      })
      .catch(() => { if (!cancelled) setStatus('error'); });

    return () => { cancelled = true; };
  }, [viewer, selectedEntityId, attribute, visible, opacity, scope, api, setStatus]);

  return null;
}

export default SoilLayer;
