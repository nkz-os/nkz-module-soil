import React, { createContext, useContext, useState, useMemo } from 'react';

export type LayerScope = 'selected' | 'all';
export type LayerStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error' | 'noSelection';

interface SoilLayerState {
  attribute: string;
  setAttribute: (a: string) => void;
  visible: boolean;
  setVisible: (v: boolean) => void;
  opacity: number;
  setOpacity: (o: number) => void;
  scope: LayerScope;
  setScope: (s: LayerScope) => void;
  status: LayerStatus;
  setStatus: (s: LayerStatus) => void;
}

const Ctx = createContext<SoilLayerState | null>(null);

export function SoilProvider({ children }: { children: React.ReactNode }) {
  const [attribute, setAttribute] = useState('usdaTextureClass');
  const [visible, setVisible] = useState(false);
  const [opacity, setOpacity] = useState(0.7);
  const [scope, setScope] = useState<LayerScope>('selected');
  const [status, setStatus] = useState<LayerStatus>('idle');
  const value = useMemo(
    () => ({ attribute, setAttribute, visible, setVisible, opacity, setOpacity, scope, setScope, status, setStatus }),
    [attribute, visible, opacity, scope, status],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSoilLayerContext(): SoilLayerState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useSoilLayerContext must be used within SoilProvider');
  return v;
}

/**
 * fetchSoilLayerContext — same-origin fetch to the soil module API (via api-gateway).
 * Uses relative /api/soil so session cookies work on nekazari.robotika.cloud.
 */
export async function fetchSoilLayerContext(path: string): Promise<any> {
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
