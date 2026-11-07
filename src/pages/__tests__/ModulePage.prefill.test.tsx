// @vitest-environment jsdom
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mockParcels = [
  {
    id: 'urn:ngsi-ld:AgriParcel:parcel-alpha',
    name: { type: 'Property', value: 'Alpha Field' },
    location: {
      type: 'Polygon',
      coordinates: [
        [
          [-2.0, 43.0],
          [-1.0, 43.0],
          [-1.0, 44.0],
          [-2.0, 44.0],
          [-2.0, 43.0],
        ],
      ],
    },
  },
  {
    id: 'urn:ngsi-ld:AgriParcel:parcel-beta',
    name: { type: 'Property', value: 'Beta Field' },
    location: {
      type: 'Point',
      coordinates: [1.25, 41.5],
    },
  },
];

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('@nekazari/viewer-kit', () => ({
  SlotShellCompact: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@nekazari/module-kit', () => ({
  useEntities: () => ({ data: mockParcels, isLoading: false }),
}));
vi.mock('@nekazari/ui-kit', () => ({
  Select: ({
    value,
    onValueChange,
    options,
  }: {
    value: string;
    onValueChange: (v: string) => void;
    options: Array<{ value: string; label: string }>;
  }) => (
    <select
      data-testid="mock-select"
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock('../../hooks/useSoilApi', () => ({
  useSoilApi: () => ({ getSummary: () => new Promise(() => {}) }),
}));
vi.mock('../../components/SoilProfileCard', () => ({
  SoilProfileCard: () => <div />,
}));

import ModulePage from '../ModulePage';

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <ModulePage />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe('ManualSamplingTab deep link prefill', () => {
  it('prefills parcel and centroid when navigating with ?parcel= and ?tab=manual', async () => {
    renderAt('/?parcel=parcel-alpha&tab=manual');

    // Expected centroid:
    // lon = (-2 + -1 + -1 + -2) / 4 = -1.500000
    // lat = (43 + 43 + 44 + 44) / 4 = 43.500000
    // depthFrom = 0, depthTo = 30
    const latInput = document.querySelector('input[type="number"]') as HTMLInputElement;
    const allNumberInputs = Array.from(document.querySelectorAll('input[type="number"]')) as HTMLInputElement[];

    expect(allNumberInputs[0].value).toBe('43.500000'); // lat
    expect(allNumberInputs[1].value).toBe('-1.500000'); // lon
    expect(allNumberInputs[2].value).toBe('0'); // depthFrom
    expect(allNumberInputs[3].value).toBe('30'); // depthTo

    const select = screen.getAllByTestId('mock-select')[0] as HTMLSelectElement;
    expect(select.value).toBe('urn:ngsi-ld:AgriParcel:parcel-alpha');
  });

  it('prefills centroid when selecting a parcel from the dropdown', () => {
    renderAt('/?tab=manual');

    const select = screen.getAllByTestId('mock-select')[0] as HTMLSelectElement;
    const allNumberInputs = Array.from(document.querySelectorAll('input[type="number"]')) as HTMLInputElement[];

    expect(allNumberInputs[0].value).toBe(''); // lat initially empty
    expect(allNumberInputs[1].value).toBe(''); // lon initially empty

    // Select parcel-beta
    fireEvent.change(select, { target: { value: 'urn:ngsi-ld:AgriParcel:parcel-beta' } });

    expect(allNumberInputs[0].value).toBe('41.500000'); // lat
    expect(allNumberInputs[1].value).toBe('1.250000'); // lon
    expect(allNumberInputs[2].value).toBe('0'); // depthFrom
    expect(allNumberInputs[3].value).toBe('30'); // depthTo

    // Manually edit lat
    fireEvent.change(allNumberInputs[0], { target: { value: '45.123456' } });

    // Switch to parcel-alpha: lat should remain user-typed
    fireEvent.change(select, { target: { value: 'urn:ngsi-ld:AgriParcel:parcel-alpha' } });
    expect(allNumberInputs[0].value).toBe('45.123456');
  });
});
