import { useEffect, useRef } from 'react';
import { useViewerOptional, useViewerLayer } from '@nekazari/sdk';
import type { GeoJsonDataSource } from 'cesium';
import { useSoilLayerContext } from '../../services/soilLayerContext';
import { useSoilApi } from '../../hooks/useSoilApi';
import { soilLayerColor } from '../../lib/soilLayerColor';

const RASTER_ATTRIBUTES = ['penetrationResistance'];

// The ambient `cesium` module types Entity.polygon as `unknown` (Cesium's
// real PolygonGraphics has far more members than this file touches — see
// src/types/cesium.d.ts). Cast to this shape only at the point each style
// property is actually set/read.
interface SoilPolygonGraphics {
  material?: unknown;
  outline?: boolean;
  outlineColor?: unknown;
  heightReference?: unknown;
  classificationType?: unknown;
}

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
  const { attribute, scope } = useSoilLayerContext();
  // Visibility, opacity (0–100) and load status come from the host's unified
  // Layers menu via the shared LayerRegistry.
  const { visible, opacity, setStatus } = useViewerLayer('soil-raster');
  const dsRef = useRef<GeoJsonDataSource | null>(null);
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
          layer.alpha = opacity / 100;
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
      imageryRef.current.alpha = opacity / 100;
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
      .then((ds: GeoJsonDataSource | null) => {
        if (!ds || cancelled || v.isDestroyed?.()) return;
        for (const ent of ds.entities.values) {
          const raw = readFeatureValue(ent.properties, Cesium);
          const hex = soilLayerColor(attribute, raw ?? null);
          const polygon = ent.polygon as SoilPolygonGraphics | undefined;
          if (!polygon) continue;
          polygon.material = Cesium.Color.fromCssColorString(hex).withAlpha(opacity / 100);
          polygon.outline = true;
          polygon.outlineColor = Cesium.Color.BLACK.withAlpha(0.45);
          polygon.heightReference = Cesium.HeightReference.CLAMP_TO_GROUND;
          polygon.classificationType = Cesium.ClassificationType.TERRAIN;
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
    const ds = dsRef.current;
    if (!viewer || isRaster || !ds || !visible) return;
    const Cesium = (window as { Cesium?: typeof import('cesium') }).Cesium;
    if (!Cesium) return;
    for (const ent of ds.entities.values) {
      const polygon = ent.polygon as SoilPolygonGraphics | undefined;
      const mat = polygon?.material as { color?: { withAlpha: (a: number) => unknown } } | undefined;
      if (polygon && mat?.color) {
        polygon.material = mat.color.withAlpha(opacity / 100);
      }
    }
    (viewer as { scene?: { requestRender: () => void } }).scene?.requestRender();
  }, [opacity, viewer, isRaster, visible, attribute]);

  return null;
}

export default SoilLayer;
