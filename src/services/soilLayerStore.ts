/**
 * Module-scoped soil layer state — shared across layer-toggle and map-layer slots
 * (each slot mounts in a separate React tree in the host viewer).
 */

export type LayerScope = 'selected' | 'all';
export type LayerStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error' | 'noSelection';

export interface SoilLayerState {
  attribute: string;
  scope: LayerScope;
}

let state: SoilLayerState = {
  attribute: 'usdaTextureClass',
  scope: 'selected',
};

const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((l) => l());
}

export function getSoilLayerState(): SoilLayerState {
  return state;
}

export function setSoilLayerState(patch: Partial<SoilLayerState>): void {
  let changed = false;
  for (const key of Object.keys(patch) as (keyof SoilLayerState)[]) {
    if (state[key] !== patch[key]) {
      changed = true;
      break;
    }
  }
  if (!changed) return;
  state = { ...state, ...patch };
  emit();
}

export function subscribeSoilLayer(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
