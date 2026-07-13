import React, { useCallback, useSyncExternalStore } from 'react';
import {
  getSoilLayerState,
  setSoilLayerState,
  subscribeSoilLayer,
  type LayerScope,
  type LayerStatus,
  type SoilLayerState,
} from './soilLayerStore';

export type { LayerScope, LayerStatus };

interface SoilLayerControls extends SoilLayerState {
  setAttribute: (a: string) => void;
  setVisible: (v: boolean) => void;
  setOpacity: (o: number) => void;
  setScope: (s: LayerScope) => void;
  setStatus: (s: LayerStatus) => void;
}

export function useSoilLayerContext(): SoilLayerControls {
  const snap = useSyncExternalStore(subscribeSoilLayer, getSoilLayerState, getSoilLayerState);

  const setAttribute = useCallback((attribute: string) => setSoilLayerState({ attribute }), []);
  const setVisible = useCallback((visible: boolean) => setSoilLayerState({ visible }), []);
  const setOpacity = useCallback((opacity: number) => setSoilLayerState({ opacity }), []);
  const setScope = useCallback((scope: LayerScope) => setSoilLayerState({ scope }), []);
  const setStatus = useCallback((status: LayerStatus) => setSoilLayerState({ status }), []);

  return {
    ...snap,
    setAttribute,
    setVisible,
    setOpacity,
    setScope,
    setStatus,
  };
}

/** Kept for module-kit withModuleProvider; state lives in soilLayerStore. */
export function SoilProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

/**
 * fetchSoilLayerContext — same-origin fetch to the soil module API (via api-gateway).
 */
export async function fetchSoilLayerContext(path: string): Promise<unknown> {
  const suffix = path.startsWith('/v1/soil')
    ? path.slice('/v1/soil'.length)
    : path.startsWith('/')
      ? path
      : `/${path}`;
  const resp = await fetch(`/api/soil${suffix}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
  if (!resp.ok) {
    const body = await resp.text().catch(() => '');
    throw new Error(`HTTP ${resp.status}${body ? ` — ${body.slice(0, 120)}` : ''}`);
  }
  return resp.json();
}
