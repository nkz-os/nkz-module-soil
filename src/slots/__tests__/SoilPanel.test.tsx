import { describe, it, expect, vi } from 'vitest';

vi.mock('@nekazari/sdk', () => ({
  useViewer: () => ({ selectedEntityId: undefined, selectedEntityType: undefined }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../hooks/useSoilApi', () => ({
  useSoilApi: () => ({
    getSummary: vi.fn().mockResolvedValue(null),
  }),
}));

import { SoilPanel } from '../SoilPanel';

describe('SoilPanel', () => {
  it('exports a component function', () => {
    expect(typeof SoilPanel).toBe('function');
  });

  it('takes no props - reads the selection via useViewer()', () => {
    expect(SoilPanel.length).toBe(0);
  });
});
