// Minimal ambient typing for the `cesium` package.
//
// This module is never bundled: Cesium is host-provided at runtime via
// `window.Cesium` (see src/components/slots/SoilLayer.tsx), and `cesium`
// itself is not a dependency of this frontend (it's a very large package —
// none of the other Nekazari modules depend on it either; they leave the
// Cesium viewer typed as `unknown`/`any`). This declaration exists solely so
// `typeof import('cesium')` type-checks, covering only the members this
// module actually references.
declare module 'cesium' {
  export class JulianDate {
    static now(): JulianDate;
  }

  export class Color {
    static readonly BLACK: Color;
    static fromCssColorString(color: string): Color;
    withAlpha(alpha: number): Color;
  }

  export enum HeightReference {
    NONE = 0,
    CLAMP_TO_GROUND = 1,
    RELATIVE_TO_GROUND = 2,
  }

  export enum ClassificationType {
    TERRAIN = 0,
    CESIUM_3D_TILE = 1,
    BOTH = 2,
  }

  export class SingleTileImageryProvider {
    constructor(options: { url: string });
  }

  export interface Entity {
    properties?: unknown;
    polygon?: unknown;
  }

  export class GeoJsonDataSource {
    entities: { values: Entity[] };
    static load(
      data: unknown,
      options?: { clampToGround?: boolean }
    ): Promise<GeoJsonDataSource>;
  }
}
