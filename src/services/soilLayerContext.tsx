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
