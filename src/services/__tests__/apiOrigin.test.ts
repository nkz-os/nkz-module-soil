import { describe, it, expect, afterEach, vi } from 'vitest';

async function load() {
  vi.resetModules();
  return (await import('../apiOrigin')).API_ORIGIN;
}

describe('API_ORIGIN', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds the soil base from window.__ENV__.VITE_API_URL', async () => {
    vi.stubGlobal('window', { __ENV__: { VITE_API_URL: 'https://api.example/' } });
    expect(`${await load()}/api/soil`).toBe('https://api.example/api/soil');
  });

  it('is same-origin without __ENV__', async () => {
    vi.stubGlobal('window', {});
    expect(`${await load()}/api/soil`).toBe('/api/soil');
  });
});
