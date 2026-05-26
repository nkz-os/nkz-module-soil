import { defineModule } from '@nekazari/module-kit';
import * as slots from './slots';
import ModulePage from './pages/ModulePage';
import { i18n } from './i18n';

export default defineModule({
  id: 'soil',
  displayName: 'Soil',
  version: '0.1.0',
  hostApiVersion: '^2.0.0',
  accent: {
    base: '#4a9e6e',
    soft: '#e8f5ee',
    strong: '#2d6b4a',
  },
  icon: 'terrain',
  main: ModulePage,
  route: '/module/soil',
  navigation: {
    label: { es: 'Suelo', en: 'Soil' },
    section: 'modules',
    priority: 40,
  },
  slots: {
    'context-panel': [slots.contextPanel],
    'provider-health-panel': [slots.providerHealthPanel],
  },
  api: { basePath: '/api/v1/soil' },
  requiredRoles: ['GestorAgricola', 'Administrador'],
  requiredPlan: 'pro',
  i18n,
  data: {
    entities: ['AgriSoilExtended', 'SoilSamplingPoint', 'SoilSurvey', 'SoilDerivedRaster'],
    timeseries: [],
  },
});
