# Local map context

The map uses local georeferenced vector context and needs no external basemap tiles.

Source: U.S. Census Bureau, Census 2020 TIGERweb State/County service. Public government geographic data.

Downloaded UTC: 2026-11-14T20:49:59.605747+00:00

Asset: `data/processed/map-context.geojson`; 63 features, 118454 bytes. Five state polygons (California, Nevada, Oregon, Arizona, Utah) and 58 California county polygons. Geometry is EPSG:4326 GeoJSON with a service generalization tolerance of 0.005 degrees, suitable for visual context, not statistical clipping or area calculation. The analytical California boundary is a separate, more detailed asset.

Feature properties: `name`, `kind` (`state` or `county`), `state_fips`, `abbreviation`, `geoid`.

Queries and source-response hashes:

- states: [5 source features](https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/State_County/MapServer/0/query?where=STATE+IN+%28%2706%27%2C%2732%27%2C%2741%27%2C%2704%27%2C%2749%27%29&outFields=NAME%2CSTATE%2CGEOID&outSR=4326&f=geojson&maxAllowableOffset=0.005&returnGeometry=true); SHA-256 `3c99fb517e99b7246d368391b6ac8d9dd0a3c92711cef15fcf392cdbe89bae64`.
- counties: [58 source features](https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/State_County/MapServer/1/query?where=STATE+%3D+%2706%27&outFields=NAME%2CSTATE%2CCOUNTY%2CGEOID&outSR=4326&f=geojson&maxAllowableOffset=0.005&returnGeometry=true); SHA-256 `ce88745ec435880f2e695fb9c019f303fabc205745125d536b5dba751d8fbb5e`.

The map contains no roads or live imagery. Labels and fire overlays are rendered separately. Retain U.S. Census Bureau attribution.
