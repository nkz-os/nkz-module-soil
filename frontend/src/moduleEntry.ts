import { defineModule } from '@nekazari/module-kit';
import { SoilPanel } from './slots/SoilPanel';
import ModulePage from './pages/ModulePage';

export default defineModule({
  id: 'soil',
  viewerSlots: {
    'context-panel': SoilPanel,
  },
  routes: [
    { path: '/module/soil', component: ModulePage },
  ],
  i18n: {
    es: {
      soil: {
        title: 'Suelo',
        summary: 'Caracterización edafológica de la parcela',
        hydrologicGroup: 'Grupo hidrológico',
        ksat: 'Conductividad hidráulica (Ksat)',
        texture: 'Textura',
        compaction: 'Compactación relativa',
        source: 'Fuente de datos',
        horizon: 'Horizonte',
        viewDetails: 'Ver más detalles',
        tabs: {
          dashboard: 'Fuentes',
          manual: 'Muestreo manual',
          csv: 'Carga CSV',
          history: 'Historial',
        },
        dashboardDescription: 'Estado de las fuentes de datos de suelo para tu tenant.',
        dashboardPlaceholder: 'Conecta fuentes de datos para empezar.',
        csvDropzone: 'Arrastra un archivo CSV o haz clic para seleccionar',
        csvFormat: 'Formato: lat, lon, depthFrom, depthTo, sand, silt, clay, organicCarbon, ph, cec, bulkDensity, coarseFragments, labReference, samplingDate',
        historyPlaceholder: 'No hay muestreos registrados todavía.',
        fields: {
          lat: 'Latitud', lon: 'Longitud',
          depthFrom: 'Profundidad desde (cm)', depthTo: 'Profundidad hasta (cm)',
          sand: 'Arena (%)', silt: 'Limo (%)', clay: 'Arcilla (%)',
          organicCarbon: 'Carbono orgánico (%)', ph: 'pH',
          bulkDensity: 'Densidad aparente (g/cm³)',
          penetrationResistance: 'Resistencia a la penetración (MPa)',
        },
        submit: 'Guardar',
        success: 'Punto de muestreo guardado correctamente.',
        error: 'Error al guardar el punto de muestreo.',
        validation: {
          textureSum: 'Arena+limo+arcilla debe sumar ~100%',
        },
      },
    },
    en: {
      soil: {
        title: 'Soil',
        summary: 'Edaphological characterization of the parcel',
        hydrologicGroup: 'Hydrologic Group',
        ksat: 'Hydraulic Conductivity (Ksat)',
        texture: 'Texture',
        compaction: 'Relative Compaction',
        source: 'Data Source',
        horizon: 'Horizon',
        viewDetails: 'View details',
        tabs: {
          dashboard: 'Sources',
          manual: 'Manual Sampling',
          csv: 'CSV Upload',
          history: 'History',
        },
        dashboardDescription: 'Status of soil data sources for your tenant.',
        dashboardPlaceholder: 'Connect data sources to get started.',
        csvDropzone: 'Drag a CSV file or click to select',
        csvFormat: 'Format: lat, lon, depthFrom, depthTo, sand, silt, clay, organicCarbon, ph, cec, bulkDensity, coarseFragments, labReference, samplingDate',
        historyPlaceholder: 'No sampling records yet.',
        fields: {
          lat: 'Latitude', lon: 'Longitude',
          depthFrom: 'Depth from (cm)', depthTo: 'Depth to (cm)',
          sand: 'Sand (%)', silt: 'Silt (%)', clay: 'Clay (%)',
          organicCarbon: 'Organic Carbon (%)', ph: 'pH',
          bulkDensity: 'Bulk Density (g/cm³)',
          penetrationResistance: 'Penetration Resistance (MPa)',
        },
        submit: 'Save',
        success: 'Sampling point saved successfully.',
        error: 'Error saving sampling point.',
        validation: {
          textureSum: 'Sand+silt+clay must sum to ~100%',
        },
      },
    },
  },
});
