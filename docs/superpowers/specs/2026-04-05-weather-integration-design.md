# Weather Integration Design Spec

## Overview

Associate weather information from Open-Meteo with timelapse captures. 15-minute interval readings + daily summaries stored in SQLite. Displayed as toggleable badges/overlays in the web UI. Filterable by conditions.

## Data Source

**Open-Meteo** (open-meteo.com) — free, no API key, supports historical data. Uses the existing `location.latitude` and `location.longitude` from config.

API endpoint: `https://api.open-meteo.com/v1/forecast` (current) and `https://archive-api.open-meteo.com/v1/archive` (historical).

Request parameters:
- `latitude`, `longitude` from config
- `minutely_15`: temperature_2m, relative_humidity_2m, precipitation, weather_code, wind_speed_10m, cloud_cover
- `daily`: temperature_2m_max, temperature_2m_min, weather_code
- `timezone`: auto

## Database Schema

New table in `jobs.py` schema:

```sql
CREATE TABLE IF NOT EXISTS weather (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,
    minute        INTEGER,
    temperature   REAL,
    conditions    TEXT,
    humidity      INTEGER,
    wind_speed    REAL,
    precipitation REAL,
    cloud_cover   INTEGER,
    temp_high     REAL,
    temp_low      REAL,
    fetched_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_weather_date_minute
    ON weather(date, minute);
```

- `minute`: minutes since midnight (0, 15, 30... 1425) for 15-min intervals. `NULL` for daily summary.
- `conditions`: human-readable string mapped from WMO weather codes (e.g. 0→"Clear sky", 61→"Light rain").
- `temp_high`/`temp_low`: populated only on daily summary rows (where `minute IS NULL`).

## WMO Weather Code Mapping

```
0: Clear sky
1: Mainly clear
2: Partly cloudy
3: Overcast
45: Fog
48: Depositing rime fog
51: Light drizzle
53: Moderate drizzle
55: Dense drizzle
61: Light rain
63: Moderate rain
65: Heavy rain
71: Light snow
73: Moderate snow
75: Heavy snow
80: Light rain showers
81: Moderate rain showers
82: Violent rain showers
95: Thunderstorm
96: Thunderstorm with light hail
99: Thunderstorm with heavy hail
```

## New Module: `src/timelapse/weather.py`

**Functions:**

`fetch_weather(latitude, longitude, date) -> dict`
- Calls Open-Meteo API for a single date
- Returns parsed dict with `daily` summary and `intervals` list (15-min readings)
- Handles API errors gracefully (returns None, logs warning)

`store_weather(db, date, weather_data)`
- Writes daily summary + 15-min intervals to the weather table
- Uses INSERT OR REPLACE to handle re-fetches

`get_weather_for_date(db, date) -> dict`
- Returns daily summary + all intervals for a date

`get_weather_for_time(db, date, minute) -> dict`
- Returns the closest 15-min reading to the given time

`backfill_weather(db, latitude, longitude, date_from, date_to)`
- Fetches historical weather for a date range
- One API call per day, with 0.5s delay between calls to be polite
- Skips dates that already have weather data

## Capture Service Integration

In `service.py` main loop, once per hour (tracked by a `last_weather_fetch` timestamp):
- Call `fetch_weather()` for today
- Call `store_weather()` to save/update
- If it fails, log warning and try again next hour

## CLI Command

```
timelapse backfill-weather --config FILE --from YYYY-MM-DD [--to YYYY-MM-DD]
```

- `--to` defaults to yesterday
- Fetches historical weather for each date in range
- Skips dates already in the database
- Reports progress: "Fetched weather for 2026-03-28 (Clear sky, 15°C)"

## Web API Endpoints

**`GET /api/weather?date=YYYY-MM-DD`**

Returns daily summary + all 15-min intervals:

```json
{
  "date": "2026-04-05",
  "summary": {
    "conditions": "Partly cloudy",
    "temp_high": 18.2,
    "temp_low": 8.1
  },
  "intervals": [
    {
      "minute": 0,
      "time": "00:00",
      "temperature": 9.1,
      "conditions": "Clear sky",
      "humidity": 82,
      "wind_speed": 8.5,
      "precipitation": 0.0,
      "cloud_cover": 12
    }
  ]
}
```

**`GET /api/weather/for-capture?captured_at=ISO`**

Returns the closest 15-min reading:

```json
{
  "temperature": 15.3,
  "conditions": "Partly cloudy",
  "humidity": 65,
  "wind_speed": 12.1,
  "precipitation": 0.0,
  "cloud_cover": 45
}
```

**`GET /api/captures?date=...&conditions=Sunny`** (extend existing)

Add optional `conditions` filter to the captures list endpoint. Matches captures whose nearest weather reading has the specified conditions.

## Frontend

### New Components (use frontend-design skill)

**`WeatherBadge.vue`**
- Props: `conditions` (string), `temperature` (number)
- Small inline badge: weather icon + temp (e.g. "☀️ 18°C")
- Used on gallery thumbnails and capture info lines

**`WeatherDetail.vue`**
- Props: `weather` (object with all fields)
- Expanded card: conditions, temp, humidity, wind, precipitation, cloud cover
- Used in ImageViewer and Compare detail panels

### Modified Views

**Gallery.vue:**
- Toggle switch in toolbar: "Weather" on/off (persisted in localStorage as `timelapse-show-weather`)
- When on: fetch weather for the displayed date, show WeatherBadge on each thumbnail (daily summary conditions + temp)
- Condition filter dropdown in toolbar (when weather toggle is on): "All", "Clear", "Cloudy", "Rain", etc.

**ImageViewer.vue:**
- When weather toggle is on: show WeatherDetail below the image info (camera name, timestamp)
- Fetches per-capture weather via `/api/weather/for-capture`

**Compare.vue:**
- When weather toggle is on: show WeatherBadge next to each selected capture's info line
- Fetches weather for both selected captures

### Toggle Persistence

```js
const showWeather = ref(localStorage.getItem('timelapse-show-weather') === 'true')
watch(showWeather, (v) => localStorage.setItem('timelapse-show-weather', v))
```

## Files to Create/Modify

### New:
- `src/timelapse/weather.py` — weather fetcher, storage, WMO mapping
- `src/timelapse/web/routes/weather.py` — API endpoints
- `frontend/src/components/WeatherBadge.vue`
- `frontend/src/components/WeatherDetail.vue`
- `tests/test_weather.py` — weather module tests
- `tests/test_web_weather.py` — API endpoint tests

### Modified:
- `src/timelapse/jobs.py` — add weather table to schema, add weather DB methods
- `src/timelapse/service.py` — hourly weather fetch in main loop
- `src/timelapse/cli.py` — add `backfill-weather` command
- `src/timelapse/web/app.py` — register weather router
- `src/timelapse/web/routes/captures.py` — add conditions filter
- `frontend/src/views/Gallery.vue` — weather toggle, badges, condition filter
- `frontend/src/views/Compare.vue` — weather toggle, badges
- `frontend/src/components/ImageViewer.vue` — weather detail
- `frontend/src/api.js` — add weather API methods

## Dependencies

**New Python package:** None — Open-Meteo API is a simple HTTP GET. Use `urllib.request` (stdlib) to avoid adding a dependency. The web service already has `httpx` in dev deps but the weather module runs in the capture service which doesn't have it.

## Error Handling

- API failure: log warning, skip. Don't crash the capture service.
- Missing weather for a date: UI shows no badge (graceful absence, not an error).
- Rate limiting: Open-Meteo allows 10,000 requests/day. At 24 calls/day (hourly) we're well within limits.
- Backfill: 0.5s delay between requests to be respectful.
