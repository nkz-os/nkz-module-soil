import { SoilPanel } from './SoilPanel';
import { ProviderHealthPanel } from './ProviderHealthPanel';

export const contextPanel = {
  id: 'context-panel',
  component: SoilPanel,
  priority: 10,
};

export const providerHealthPanel = {
  id: 'provider-health-panel',
  component: ProviderHealthPanel,
  priority: 5,
};
