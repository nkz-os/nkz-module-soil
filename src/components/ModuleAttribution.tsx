import React from 'react';
import { useTranslation } from 'react-i18next';

/** FIWARE / NKZ / AGPL attribution for module slot panels (AGENTS.md). */
export function ModuleAttribution() {
  const { t } = useTranslation('soil');
  return (
    <p className="text-nkz-xs text-nkz-muted mt-2 pt-2 border-t border-nkz-border/50">
      {t('attribution.platform')}
    </p>
  );
}
