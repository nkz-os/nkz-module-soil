import React from 'react';
import { SoilPanel } from './SoilPanel';
import { SoilLayer } from '../components/slots/SoilLayer';
import { SoilLayerToggle } from '../components/slots/SoilLayerToggle';
import { SoilProvider } from '../services/soilLayerContext';

type SlotType = 'entity-tree' | 'map-layer' | 'context-panel' | 'bottom-panel' | 'layer-toggle' | 'dashboard-widget';

interface SlotWidgetDefinition {
  id: string;
  moduleId?: string;
  component: string;
  priority: number;
  localComponent: React.ComponentType<any>;
  defaultProps?: Record<string, any>;
  showWhen?: { entityType?: string[]; layerActive?: string[] };
}

type ModuleViewerSlots = Record<SlotType, SlotWidgetDefinition[]> & {
  moduleProvider?: React.ComponentType<{ children: React.ReactNode }>;
};

const MODULE_ID = 'soil';

export const moduleSlots: ModuleViewerSlots = {
  'map-layer': [
    { id: 'soil-cesium-layer', moduleId: MODULE_ID, component: 'SoilLayer', priority: 10, localComponent: SoilLayer },
  ],
  'layer-toggle': [
    { id: 'soil-layer-toggle', moduleId: MODULE_ID, component: 'SoilLayerToggle', priority: 20,
      localComponent: SoilLayerToggle, showWhen: { entityType: ['AgriParcel'] } },
  ],
  'context-panel': [
    { id: 'soil-context-panel', moduleId: MODULE_ID, component: 'SoilPanel', priority: 10, localComponent: SoilPanel },
  ],
  'bottom-panel': [],
  'entity-tree': [],
  'dashboard-widget': [],
  moduleProvider: SoilProvider,
};

export default moduleSlots;
