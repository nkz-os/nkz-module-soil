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
  setScope: (s: LayerScope) => void;
}

export function useSoilLayerContext(): SoilLayerControls {
  const snap = useSyncExternalStore(subscribeSoilLayer, getSoilLayerState, getSoilLayerState);

  const setAttribute = useCallback((attribute: string) => setSoilLayerState({ attribute }), []);
  const setScope = useCallback((scope: LayerScope) => setSoilLayerState({ scope }), []);

  return {
    ...snap,
    setAttribute,
    setScope,
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
