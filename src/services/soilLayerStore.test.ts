import { describe, expect, it, vi } from 'vitest';
import {
  getSoilLayerState,
  setSoilLayerState,
  subscribeSoilLayer,
} from './soilLayerStore';

describe('soilLayerStore', () => {
  it('does not notify listeners when state is unchanged', () => {
    const listener = vi.fn();
    subscribeSoilLayer(listener);
    listener.mockClear();

    setSoilLayerState({ status: getSoilLayerState().status });

    expect(listener).not.toHaveBeenCalled();
  });

  it('notifies listeners when state changes', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeSoilLayer(listener);
    listener.mockClear();

    setSoilLayerState({ status: 'loading' });

    expect(listener).toHaveBeenCalledTimes(1);
    expect(getSoilLayerState().status).toBe('loading');

    unsubscribe();
    setSoilLayerState({ status: 'ready' });
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
