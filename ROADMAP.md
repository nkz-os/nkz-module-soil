# Roadmap & Known Limitations

Tracked enhancements for the Soil module. Contributions welcome.

## Viewer

### Viewport (bbox) filtering for the soil map layer

**Status:** planned · **Priority:** scales with tenant size

The soil map layer (parcel choropleth) is served by
`GET /api/v1/soil/layers/parcels.geojson`, which currently returns **all** of a
tenant's parcels in one `FeatureCollection`. This is fine for the typical case
(tens of parcels), but for tenants with many hundreds of parcels the payload and
the number of Cesium polygons can degrade map performance, especially in the
`all` scope.

**Planned approach** (note: pagination is *not* appropriate for a map layer —
the viewer needs every in-view feature at once):

1. Add an optional `?bbox=minLon,minLat,maxLon,maxLat` query parameter to the
   endpoint and filter server-side (e.g. PostGIS `ST_Intersects` against the
   parcel geometry / bbox).
2. Have the frontend layer recompute the request on map movement
   (Cesium `camera.changed`, debounced) and pass the current view extent.
3. Optionally simplify geometries for dense polygons
   (`ST_SimplifyPreserveTopology`) to reduce payload and draw cost.

Defer until a deployment actually hits the limit; until then the all-parcels
response keeps the implementation simpler (YAGNI).

## Internationalization

- The viewer layer menu strings (`layer.*`) currently ship `es` + `en`. The
  module also bundles additional locales — extend `layer.*` (and any new keys)
  to all bundled locales for full coverage.

## Frontend tooling

- The frontend has unit tests for pure helpers (e.g. `soilLayerColor`) but no
  test runner wired into CI. Add a test runner + script so frontend logic is
  gated like the backend suite.
