import { useEffect, useRef } from 'react';
import { useViewerOptional } from '@nekazari/sdk';
import { useSoilLayerContext } from '../../services/soilLayerContext';
import { useSoilApi } from '../../hooks/useSoilApi';
import { soilLayerColor } from '../../lib/soilLayerColor';

const RASTER_ATTRIBUTES = ['penetrationResistance'];

function readFeatureValue(properties: unknown, Cesium: typeof import('cesium')): string | number | null {
  if (!properties || typeof properties !== 'object') return null;
  const bag = properties as { value?: { getValue?: (t: unknown) => unknown } };
  const prop = bag.value;
  if (prop?.getValue) {
    const raw = prop.getValue(Cesium.JulianDate.now());
    return raw as string | number | null;
  }
  return null;
}

export function SoilLayer() {
  const viewerCtx = useViewerOptional();
  const viewer = (viewerCtx as { cesiumViewer?: unknown })?.cesiumViewer;
  const selectedEntityId = (viewerCtx as { selectedEntityId?: string | null })?.selectedEntityId;
  const api = useSoilApi();
  const { attribute, visible, opacity, scope, setStatus } = useSoilLayerContext();
  const dsRef = useRef<{ destroy?: () => void } | null>(null);
  const imageryRef = useRef<{ alpha?: number } | null>(null);

  const isRaster = RASTER_ATTRIBUTES.includes(attribute);

  const removeDataSource = (v: { dataSources?: { remove: (ds: unknown, destroy?: boolean) => void }; isDestroyed?: () => boolean }) => {
    if (!dsRef.current || v.isDestroyed?.()) return;
    try {
      v.dataSources?.remove(dsRef.current, true);
    } catch {
      /* viewer torn down */
    }
    dsRef.current = null;
  };

  // ── Raster layer (penetrometer) ──────────────────────────────────────
  useEffect(() => {
    if (!viewer || isRaster) return;
    const v = viewer as { imageryLayers?: { remove: (l: unknown, destroy?: boolean) => void }; isDestroyed?: () => boolean };
    if (imageryRef.current && !v.isDestroyed?.()) {
      try {
        v.imageryLayers?.remove(imageryRef.current, true);
      } catch {
        /* destroyed */
      }
      imageryRef.current = null;
    }
  }, [viewer, isRaster]);

  useEffect(() => {
    if (!viewer || !isRaster) return;
    const Cesium = (window as { Cesium?: typeof import('cesium') }).Cesium;
    if (!Cesium) return;
    const v = viewer as {
      imageryLayers?: { remove: (l: unknown, destroy?: boolean) => void; addImageryProvider: (p: unknown) => { alpha?: number } };
      isDestroyed?: () => boolean;
    };

    if (imageryRef.current) {
      try {
        v.imageryLayers?.remove(imageryRef.current, true);
      } catch {
        /* destroyed */
      }
      imageryRef.current = null;
    }

    if (!visible) {
      setStatus('idle');
      return;
    }

    const parcel = scope === 'selected' && selectedEntityId
      ? selectedEntityId.split(':').pop()
      : undefined;
    if (scope === 'selected' && !parcel) {
      setStatus('noSelection');
      return;
    }
    if (!parcel) {
      setStatus('empty');
      return;
    }

    let cancelled = false;
    setStatus('loading');

    api.get<{ url: string }>(`/v1/soil/parcel/${parcel}/raster?property=${attribute}&depth=0-30`)
      .then((data) => {
        if (cancelled || v.isDestroyed?.()) return;
        const layer = v.imageryLayers?.addImageryProvider(
          new Cesium.SingleTileImageryProvider({ url: data.url }),
        );
        if (layer) {
          layer.alpha = opacity;
          imageryRef.current = layer;
        }
        setStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setStatus('empty');
      });

    return () => {
      cancelled = true;
    };
  }, [viewer, selectedEntityId, attribute, visible, opacity, scope, api, setStatus, isRaster]);

  useEffect(() => {
    if (imageryRef.current && isRaster) {
      imageryRef.current.alpha = opacity;
    }
  }, [opacity, isRaster]);

  // ── GeoJSON choropleth ─────────────────────────────────────────────
  useEffect(() => {
    if (!viewer || isRaster) return;
    const Cesium = (window as { Cesium?: typeof import('cesium') }).Cesium;
    if (!Cesium) return;
    const v = viewer as {
      dataSources?: { add: (ds: unknown) => void; remove: (ds: unknown, destroy?: boolean) => void };
      scene?: { requestRender: () => void };
      isDestroyed?: () => boolean;
    };

    removeDataSource(v);

    if (!visible) {
      setStatus('idle');
      return;
    }

    const parcel = scope === 'selected' && selectedEntityId
      ? selectedEntityId.split(':').pop()
      : undefined;
    if (scope === 'selected' && !parcel) {
      setStatus('noSelection');
      return;
    }

    let cancelled = false;
    setStatus('loading');

    api.getParcelsGeoJson(attribute, scope, parcel)
      .then((fc) => {
        if (cancelled || v.isDestroyed?.()) return null;
        const count = (fc as { features?: unknown[] })?.features?.length ?? 0;
        if (count === 0) {
          setStatus('empty');
          return null;
        }
        return Cesium.GeoJsonDataSource.load(fc, { clampToGround: true });
      })
      .then((ds: { entities: { values: Array<{ polygon?: unknown; properties?: unknown }> } } | null) => {
        if (!ds || cancelled || v.isDestroyed?.()) return;
        for (const ent of ds.entities.values) {
          const raw = readFeatureValue(ent.properties, Cesium);
          const hex = soilLayerColor(attribute, raw ?? null);
          if (!ent.polygon) continue;
          const poly = ent.polygon as {
            material?: unknown;
            outline?: boolean;
            outlineColor?: unknown;
            heightReference?: unknown;
            classificationType?: unknown;
          };
          poly.material = Cesium.Color.fromCssColorString(hex).withAlpha(opacity);
          poly.outline = true;
          poly.outlineColor = Cesium.Color.BLACK.withAlpha(0.45);
          poly.heightReference = Cesium.HeightReference.CLAMP_TO_GROUND;
          poly.classificationType = Cesium.ClassificationType.TERRAIN;
        }
        v.dataSources?.add(ds);
        dsRef.current = ds;
        setStatus('ready');
        v.scene?.requestRender();
      })
      .catch(() => {
        if (!cancelled) setStatus('error');
      });

    return () => {
      cancelled = true;
      removeDataSource(v);
    };
  }, [viewer, selectedEntityId, attribute, visible, opacity, scope, api, setStatus, isRaster]);

  // Opacity-only update for vector layer
  useEffect(() => {
    if (!viewer || isRaster || !dsRef.current || !visible) return;
    const Cesium = (window as { Cesium?: typeof import('cesium') }).Cesium;
    if (!Cesium) return;
    const ds = dsRef.current as { entities?: { values: Array<{ polygon?: { material?: { color?: { withAlpha: (a: number) => unknown } } } }> } } };
    if (!ds.entities) return;
    for (const ent of ds.entities.values) {
      const mat = ent.polygon?.material as { color?: { withAlpha: (a: number) => unknown } } | undefined;
      if (mat?.color) {
        ent.polygon!.material = mat.color.withAlpha(opacity) as typeof ent.polygon.material;
      }
    }
    (viewer as { scene?: { requestRender: () => void } }).scene?.requestRender();
  }, [opacity, viewer, isRaster, visible, attribute]);

  return null;
}

export default SoilLayer;
