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

    setSoilLayerState({ attribute: getSoilLayerState().attribute });

    expect(listener).not.toHaveBeenCalled();
  });

  it('notifies listeners when state changes', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeSoilLayer(listener);
    listener.mockClear();

    setSoilLayerState({ scope: 'all' });

    expect(listener).toHaveBeenCalledTimes(1);
    expect(getSoilLayerState().scope).toBe('all');

    unsubscribe();
    setSoilLayerState({ scope: 'selected' });
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
