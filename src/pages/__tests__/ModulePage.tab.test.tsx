// @vitest-environment jsdom
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('@nekazari/viewer-kit', () => ({
  SlotShellCompact: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@nekazari/module-kit', () => ({
  useEntities: () => ({ data: [], isLoading: false }),
}));
vi.mock('@nekazari/ui-kit', () => ({
  Select: () => <div />,
}));
vi.mock('../../hooks/useSoilApi', () => ({
  useSoilApi: () => ({ getSummary: () => new Promise(() => {}) }),
}));
vi.mock('../../components/SoilProfileCard', () => ({
  SoilProfileCard: () => <div />,
}));

import ModulePage from '../ModulePage';

const ACTIVE = 'border-nkz-accent-base';

function activeTabLabel(): string {
  const active = screen
    .getAllByRole('button')
    .filter((b) => b.className.split(' ').includes(ACTIVE));
  expect(active).toHaveLength(1);
  return active[0].textContent ?? '';
}

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <ModulePage />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe('ModulePage ?tab= deep link', () => {
  it('opens the manual analysis tab with ?tab=manual', () => {
    renderAt('/?tab=manual');
    expect(activeTabLabel()).toBe('tabs.manual');
  });

  it('keeps ?parcel and still opens the manual tab', () => {
    renderAt('/?parcel=abc&tab=manual');
    expect(activeTabLabel()).toBe('tabs.manual');
  });

  it('?parcel alone still opens the dashboard', () => {
    renderAt('/?parcel=abc');
    expect(activeTabLabel()).toBe('tabs.dashboard');
  });

  it('ignores an unknown tab value', () => {
    renderAt('/?tab=nope');
    expect(activeTabLabel()).toBe('tabs.dashboard');
  });
});
