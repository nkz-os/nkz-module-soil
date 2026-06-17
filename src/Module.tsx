import { defineModule, withModuleProvider } from '@nekazari/module-kit';
import { moduleSlots } from './slots';
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
  slots: withModuleProvider(moduleSlots as never) as never,
  api: { basePath: '/api/soil' },
  requiredRoles: ['GestorAgricola', 'Administrador'],
  requiredPlan: 'pro',
  i18n,
  data: {
    entities: ['AgriParcel', 'AgriSoilExtended', 'SoilSamplingPoint', 'SoilSurvey', 'SoilDerivedRaster', 'SoilWaterBudget'],
    timeseries: [],
  },
});
