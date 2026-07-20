# Spotter - US Route & Fuel Planning API

Production-quality Django API that plans a driving route between two US locations, returns map geometry, and recommends cost-optimal fuel stops along the route based on the provided fuel price dataset.

## Features

- Plan a US driving route from start to finish (address string or coordinates)
- Return route geometry as GeoJSON suitable for map rendering
- Recommend cost-optimal fuel stops for a vehicle with a **500-mile range** and **10 MPG**
- Calculate **total fuel spend** at recommended stops
- Fast responses with **one routing API call** per request (plus optional geocoding when addresses are supplied)
- Cross-country route planning completes in ~1-2 seconds locally after fuel data is loaded
- Consistent error handling, request IDs, health checks, throttling, and automated tests
- **Interactive web UI** with live map, route visualization, and fuel stop details

## Technology Stack

| Layer | Choice |
|---|---|
| Framework | Django 5.2 (latest stable) |
| API | Django REST Framework |
| Database | SQLite (development / assessment) |
| Routing | [OSRM](https://project-osrm.org/) public API |
| Geocoding | OpenStreetMap Nominatim (runtime, for addresses) |
| Fuel station geocoding | Offline GeoNames seed (`data/geocode_seed.json`) |
| HTTP client | httpx |
| Tests | pytest, pytest-django |
| Lint/format | ruff |
| CI | GitHub Actions |
| Containers | Docker + Docker Compose |

## Architecture Overview

The project follows a layered design with clear domain boundaries:

```text
API View (apps/routing/views.py)
    ↓
RoutePlannerService (orchestration)
    ↓
├── GeocodingClient (Nominatim)          - start/finish only
├── RoutingClient (OSRM)                   - one call per request
├── FuelStationRepository                  - local DB lookup
└── FuelOptimizer                          - min-cost refueling DP
```

**Key design choices**

1. **External API minimization**: If clients send coordinates, the API makes exactly **one** external call (OSRM). Address inputs require up to **two** Nominatim calls plus one OSRM call.
2. **Fuel prices are local**: The assessment CSV is loaded into SQLite with coordinates resolved offline from GeoNames, avoiding runtime geocoding for ~6,800 stations.
3. **Fuel optimization**: Stations along the route corridor are projected onto the route, then a dynamic-programming algorithm finds the minimum-cost refueling plan under the 500-mile range constraint.
4. **Dependency injection**: Clients and repositories are injectable for testing.

## Folder Structure

```text
Spotter/
├── apps/
│   ├── core/           # Shared constants, geo utils, health check, middleware
│   ├── fuel/           # Fuel models, repository, optimizer, CSV loader
│   └── routing/        # OSRM client, route planner service, API endpoints
├── config/             # Django settings and root URLs
├── data/
│   └── geocode_seed.json
├── scripts/
│   └── build_geocode_seed.py
├── fuel-prices-for-be-assessment.csv
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── requirements.txt
```

## Setup Instructions

### Prerequisites

- Python 3.11+
- Make (optional, recommended)

### Quick start

```bash
git clone <repo-url>
cd Spotter
make setup
make dev
```

`make setup` will:

1. Create a virtual environment
2. Install dependencies
3. Copy `.env.example` to `.env`
4. Run migrations
5. Load fuel stations from the CSV

### Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py load_fuel_stations
python manage.py runserver
```

Open the interactive map UI at **http://127.0.0.1:8000/** (API remains at `/api/v1/`).

### Rebuild geocode seed (optional)

If you replace the fuel CSV or want to refresh coordinates:

```bash
python scripts/build_geocode_seed.py
python manage.py load_fuel_stations --clear
```

## Environment Variables

See `.env.example` for all supported settings:

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | Django secret key | required |
| `DEBUG` | Debug mode | `True` |
| `ALLOWED_HOSTS` | Allowed hostnames | `localhost,127.0.0.1` |
| `OSRM_BASE_URL` | OSRM router base URL | `https://router.project-osrm.org` |
| `NOMINATIM_BASE_URL` | Nominatim base URL | `https://nominatim.openstreetmap.org` |
| `NOMINATIM_USER_AGENT` | Required Nominatim UA | project identifier |
| `VEHICLE_RANGE_MILES` | Max range on full tank | `500` |
| `VEHICLE_MPG` | Fuel efficiency | `10` |
| `ROUTE_CORRIDOR_MILES` | Max distance from route to consider a station | `50` |
| `HTTP_TIMEOUT_SECONDS` | External HTTP timeout | `15` |
| `FUEL_PRICES_CSV_PATH` | Fuel CSV path | `fuel-prices-for-be-assessment.csv` |

## Running Tests

```bash
make test
# or
pytest
```

## Linting & Formatting

```bash
make lint
make format
```

## Docker

```bash
make docker-up
# API available at http://localhost:8000
make docker-down
```

## API Documentation

### Web UI

`GET /`

Interactive route planner with Leaflet map, trip stats, and clickable fuel stop list.

### Health check

`GET /api/v1/health/`

### Plan route

`POST /api/v1/routes/plan/`

**Request body**

```json
{
  "start": "New York, NY",
  "finish": {"lat": 38.9072, "lng": -77.0369, "label": "Washington, DC"}
}
```

Both `start` and `finish` accept either:

- a US address string, or
- an object with `lat`/`latitude` and `lng`/`longitude`

**Successful response (`200`)**

```json
{
  "start": {"label": "New York, NY", "location": {"type": "Point", "coordinates": [-74.006, 40.7128]}},
  "finish": {"label": "Washington, DC", "location": {"type": "Point", "coordinates": [-77.0369, 38.9072]}},
  "route": {"type": "LineString", "coordinates": [[...]]},
  "map": {"type": "FeatureCollection", "features": [...]},
  "distance_miles": 225.5,
  "duration_seconds": 14400.0,
  "fuel_stops": [
    {
      "station_id": 123,
      "name": "Example Travel Center",
      "retail_price": 3.10,
      "gallons_purchased": 20.0,
      "fuel_cost_usd": 62.0,
      "location": {"type": "Point", "coordinates": [-75.1652, 39.9526]}
    }
  ],
  "total_fuel_cost_usd": 62.0,
  "total_gallons_consumed": 22.55,
  "vehicle": {"range_miles": 500, "mpg": 10},
  "request_id": "..."
}
```

**Error response shape**

```json
{
  "error": {
    "code": "validation_error",
    "message": "...",
    "details": {...}
  },
  "request_id": "..."
}
```

Common status codes:

- `400` validation errors
- `422` business-rule violations (e.g. unreachable destination)
- `502` upstream invalid response
- `503` upstream unavailable

## Design Decisions

| Decision | Rationale |
|---|---|
| OSRM for routing | Free, fast, widely used, single-call route + geometry |
| Offline fuel geocoding | Avoids thousands of runtime geocoding calls and rate limits |
| Dynamic programming optimizer | Finds minimum fuel cost under range constraints |
| SQLite | Zero-config for assessment reviewers |
| GeoJSON map payload | Directly usable by map clients (Leaflet, Mapbox GL, etc.) |

## Assumptions

1. The vehicle **starts with a full tank**; fuel cost counts purchases at recommended stops only.
2. For trips under 500 miles, **no fuel stops** are required and fuel cost is `$0.00`.
3. Fuel stations are matched to routes using city/state coordinates (GeoNames), not exact street addresses.
4. When multiple price records exist for the same station, the **lowest price** is used.
5. Only **US locations** are supported.

## Trade-offs

- City-level geocoding is less precise than street-level geocoding, but is reliable and fast for corridor matching.
- The optimizer assumes fuel is purchased only at selected stops along the optimal path.
- Public OSRM/Nominatim endpoints are suitable for assessment/demo usage; production would use self-hosted or paid providers.

## Known Limitations

- ~128 city/state pairs in the CSV could not be matched to GeoNames exactly.
- Public geocoding/routing APIs may rate-limit heavy usage.
- No authentication is implemented (not required by the assessment).

## Future Improvements

- Self-hosted OSRM / Pelias / Nominatim instances
- PostGIS for spatial indexing and exact corridor queries
- Caching of route responses
- OpenAPI schema generation with `drf-spectacular`
- Authentication and per-user rate limits

## Security Considerations

- Secrets loaded from environment variables
- `.env` excluded from version control
- DRF throttling enabled
- Production security headers configured when `DEBUG=False`
- Error responses avoid stack traces and internal details

## Testing Strategy

- Unit tests for geo utilities and fuel optimizer
- API tests with mocked planner for validation and error handling
- Integration test for route planner with stubbed routing client and seeded DB stations
- External APIs mocked at service boundaries; no live network dependency in CI
