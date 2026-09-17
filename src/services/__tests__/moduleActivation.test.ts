import { describe, it, expect, vi } from 'vitest';

const mockPost = vi.fn();

vi.mock('@nekazari/sdk', () => ({
  NKZClient: vi.fn().mockImplementation(() => ({
    post: mockPost,
  })),
}));

import { activateSoilForParcel } from '../moduleActivation';

describe('activateSoilForParcel', () => {
  it('POSTs to the entity-manager activate endpoint for the soil module', async () => {
    mockPost.mockResolvedValueOnce({ message: 'Module soil activated', setup_status: 'ok' });
    const result = await activateSoilForParcel('urn:ngsi-ld:AgriParcel:abc');
    expect(mockPost).toHaveBeenCalledWith(
      '/api/entities/parcels/urn:ngsi-ld:AgriParcel:abc/modules/soil/activate',
      {}
    );
    expect(result.setup_status).toBe('ok');
  });
});
