import { defineModule } from '@nekazari/module-kit';
import * as slots from './slots';
import ModulePage from './pages/ModulePage';
import { i18n } from './i18n';

export default defineModule({
  id: 'soil',
  displayName: 'Soil',
  version: '0.1.0',
  hostApiVersion: '1.0.0',
  accent: '#4a9e6e',
  icon: 'terrain',
  main: ModulePage,
  route: { path: '/module/soil' },
  navigation: { label: 'soil.title', order: 40 },
  slots,
  api: { baseUrl: '/api/v1/soil' },
  requiredRoles: ['GestorAgricola', 'Administrador'],
  requiredPlan: 2,
  i18n,
  data: {
    entities: ['AgriSoil', 'SoilSamplingPoint', 'SoilSurvey', 'SoilDerivedRaster'],
    timeseries: [],
  },
});
