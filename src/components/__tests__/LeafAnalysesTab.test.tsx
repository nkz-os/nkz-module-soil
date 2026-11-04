// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, p?: Record<string, unknown>) => (p ? `${key} ${JSON.stringify(p)}` : key) }),
}));
vi.mock('@nekazari/module-kit', () => ({
  useEntities: () => ({ data: [{ id: 'urn:ngsi-ld:AgriParcel:demo-parcel-001', name: { value: 'Demo' } }], isLoading: false }),
}));
const api = {
  previewLeafCsv: vi.fn(),
  importLeafCsv: vi.fn(),
  listZonings: vi.fn(),
  exportLeafCsv: vi.fn(),
};
vi.mock('../../hooks/useSoilApi', () => ({ useSoilApi: () => api }));

import { LeafAnalysesTab } from '../LeafAnalysesTab';

const PREVIEW = {
  accepted: [{ row: 2, id: 's1', plantCodes: ['T-1'], dateSampled: '2026-07-15' }],
  rejected: [{ row: 3, error: 'Row 3: unknown plant code T-9 in this parcel' }],
  warnings: [], created: 0,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.previewLeafCsv.mockResolvedValue(PREVIEW);
  api.importLeafCsv.mockResolvedValue({ ...PREVIEW, created: 1 });
  api.listZonings.mockResolvedValue([
    { run_id: 'veg-1', method: 'vegetationIndex', date: '2026-05-01', zone_count: 4, labels: [], is_default: true },
    { run_id: 'manual-abc', method: 'manual', date: '2026-06-01', zone_count: 2, labels: ['T1', 'T2'], is_default: false },
  ]);
  api.exportLeafCsv.mockResolvedValue(new Blob(['a,b\n']));
});
afterEach(cleanup);

function choose() {
  fireEvent.change(screen.getByLabelText('leaf.parcel'), { target: { value: 'urn:ngsi-ld:AgriParcel:demo-parcel-001' } });
}

describe('LeafAnalysesTab', () => {
  it('asks for a parcel first', () => {
    render(<LeafAnalysesTab />);
    expect(screen.getByText('leaf.chooseParcel')).toBeTruthy();
    expect(screen.queryByLabelText('leaf.file')).toBeNull();
  });

  it('previews a CSV, shows what is left out, then imports on confirm', async () => {
    render(<LeafAnalysesTab />);
    choose();
    fireEvent.change(screen.getByLabelText('leaf.file'), { target: { files: [new File(['x'], 'leaf.csv')] } });
    await waitFor(() => expect(api.previewLeafCsv).toHaveBeenCalled());
    expect(api.previewLeafCsv.mock.calls[0][0]).toBe('urn:ngsi-ld:AgriParcel:demo-parcel-001');
    expect((await screen.findByTestId('leaf-rejected')).textContent).toContain('T-9');
    expect(api.importLeafCsv).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('leaf.import'));
    await waitFor(() => expect(api.importLeafCsv).toHaveBeenCalled());
    expect((await screen.findByRole('status')).textContent).toContain('"count":1');
  });

  it('exports with the chosen zoning (default preselected)', async () => {
    render(<LeafAnalysesTab />);
    choose();
    const zoning = (await screen.findByLabelText('leaf.zoning')) as HTMLSelectElement;
    await waitFor(() => expect(zoning.value).toBe('veg-1'));
    fireEvent.change(zoning, { target: { value: 'manual-abc' } });
    fireEvent.click(screen.getByText('leaf.export'));
    await waitFor(() => expect(api.exportLeafCsv).toHaveBeenCalledWith('urn:ngsi-ld:AgriParcel:demo-parcel-001', 'manual-abc'));
  });

  it('"no zones" really exports without zones, also when zonings cannot be listed', async () => {
    api.listZonings.mockRejectedValue(new Error('down'));
    render(<LeafAnalysesTab />);
    choose();
    const zoning = (await screen.findByLabelText('leaf.zoning')) as HTMLSelectElement;
    expect(zoning.value).toBe('none');
    fireEvent.click(screen.getByText('leaf.export'));
    await waitFor(() => expect(api.exportLeafCsv).toHaveBeenCalledWith('urn:ngsi-ld:AgriParcel:demo-parcel-001', 'none'));
  });

  it('shows each warning by its kind and how many samples will be overwritten', async () => {
    api.previewLeafCsv.mockResolvedValue({
      ...PREVIEW,
      accepted: [{ ...PREVIEW.accepted[0], action: 'update' }],
      warnings: [{ code: 'ignored_column', column: 'Notes' }, { code: 'stored_as_other', column: 'N total (%)' }],
    });
    render(<LeafAnalysesTab />);
    choose();
    fireEvent.change(screen.getByLabelText('leaf.file'), { target: { files: [new File(['x'], 'leaf.csv')] } });
    expect(await screen.findByText('leaf.storedAsOther {"column":"N total (%)"}')).toBeTruthy();
    expect(screen.getByText('leaf.ignoredColumn {"column":"Notes"}')).toBeTruthy();
    expect(screen.getByText('leaf.updates {"count":1}')).toBeTruthy();
  });
});
