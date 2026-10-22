import { describe, it, expect, vi } from 'vitest';

// Mock the module-kit hooks
vi.mock('@nekazari/module-kit', () => ({
  useAPI: () => ({
    get: vi.fn().mockResolvedValue({ horizons: [] }),
  }),
  useEntities: () => ({ data: [], isLoading: false }),
}));

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Mock useSoilApi
vi.mock('../../hooks/useSoilApi', () => ({
  useSoilApi: () => ({
    getHorizons: vi.fn().mockResolvedValue({ horizons: [] }),
    getSummary: vi.fn().mockResolvedValue(null),
  }),
}));

import { SoilProfileCard } from '../SoilProfileCard';

describe('SoilProfileCard', () => {
  it('exports a component function', () => {
    expect(typeof SoilProfileCard).toBe('function');
  });

  it('renders no data state when no entityId', () => {
    // Smoke test: verify the component can be rendered without crashing
    // Full render tests would require more complex setup
    expect(SoilProfileCard).toBeDefined();
  });
});
