import React, { createContext, useContext, useState, useMemo } from 'react';

export type LayerScope = 'selected' | 'all';

interface SoilLayerState {
  attribute: string;
  setAttribute: (a: string) => void;
  visible: boolean;
  setVisible: (v: boolean) => void;
  opacity: number;
  setOpacity: (o: number) => void;
  scope: LayerScope;
  setScope: (s: LayerScope) => void;
}

const Ctx = createContext<SoilLayerState | null>(null);

export function SoilProvider({ children }: { children: React.ReactNode }) {
  const [attribute, setAttribute] = useState('usdaTextureClass');
  const [visible, setVisible] = useState(false);
  const [opacity, setOpacity] = useState(0.7);
  const [scope, setScope] = useState<LayerScope>('selected');
  const value = useMemo(
    () => ({ attribute, setAttribute, visible, setVisible, opacity, setOpacity, scope, setScope }),
    [attribute, visible, opacity, scope],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSoilLayerContext(): SoilLayerState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useSoilLayerContext must be used within SoilProvider');
  return v;
}
