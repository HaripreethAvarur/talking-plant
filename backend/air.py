"""Place lookups and outdoor air quality, from free APIs that need no key.

- us_aqi(zip): ZIP -> latitude/longitude via api.zippopotam.us, then the current US AQI
  from Open-Meteo's air-quality API (cached for 30 minutes).
- zip_for(lat, lon): the browser's location -> a US ZIP code via OpenStreetMap Nominatim.
- sun_times(zip): today's local sunrise and sunset from Open-Meteo (cached for 6 hours).
- weather(zip): current outdoor temperature, humidity and conditions (cached for 15 minutes).

Any failure returns None.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

log = logging.getLogger(__name__)

AQI_CACHE_SECONDS = 30 * 60
SUN_CACHE_SECONDS = 6 * 60 * 60
WEATHER_CACHE_SECONDS = 15 * 60
_places: dict[str, tuple[float, float]] = {}
_aqi: dict[str, tuple[float, float]] = {}  # zip -> (fetched_at, aqi)
_sun: dict[str, tuple[float, tuple[datetime, datetime]]] = {}  # zip -> (fetched_at, (sunrise, sunset))
_weather: dict[str, tuple[float, "Weather"]] = {}


async def _place(client: httpx.AsyncClient, zip_code: str) -> tuple[float, float]:
    if zip_code not in _places:
        response = await client.get(f"https://api.zippopotam.us/us/{zip_code}")
        response.raise_for_status()
        place = response.json()["places"][0]
        _places[zip_code] = (float(place["latitude"]), float(place["longitude"]))
    return _places[zip_code]


async def us_aqi(zip_code: str) -> float | None:
    cached = _aqi.get(zip_code)
    if cached and time.monotonic() - cached[0] < AQI_CACHE_SECONDS:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            latitude, longitude = await _place(client, zip_code)
            response = await client.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params={"latitude": latitude, "longitude": longitude, "current": "us_aqi"},
            )
            response.raise_for_status()
            value = response.json()["current"]["us_aqi"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        log.warning("Air quality unavailable for %s: %s", zip_code, exc)
        return None
    if value is None:
        return None
    _aqi[zip_code] = (time.monotonic(), float(value))
    return float(value)


async def zip_for(latitude: float, longitude: float) -> str | None:
    """The US ZIP code at a location (used by "use my current location" at sign-up)."""
    try:
        async with httpx.AsyncClient(
            timeout=10, headers={"User-Agent": "talking-plant/1.0 (MHacks)"}
        ) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "format": "jsonv2",
                    "zoom": 18,
                    "addressdetails": 1,
                },
            )
            response.raise_for_status()
            address = response.json().get("address", {})
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Reverse geocoding failed: %s", exc)
        return None
    postcode = (address.get("postcode") or "")[:5]
    if address.get("country_code") != "us" or not (len(postcode) == 5 and postcode.isdigit()):
        return None
    return postcode


async def sun_times(zip_code: str) -> tuple[datetime, datetime] | None:
    """Today's sunrise and sunset at the ZIP code, as local timezone-aware datetimes."""
    cached = _sun.get(zip_code)
    if cached and time.monotonic() - cached[0] < SUN_CACHE_SECONDS:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            latitude, longitude = await _place(client, zip_code)
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "daily": "sunrise,sunset",
                    "timezone": "auto",
                    "forecast_days": 1,
                },
            )
            response.raise_for_status()
            data = response.json()
            zone = ZoneInfo(data["timezone"])
            sunrise, sunset = (
                datetime.fromisoformat(data["daily"][key][0]).replace(tzinfo=zone)
                for key in ("sunrise", "sunset")
            )
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        log.warning("Sunrise/sunset unavailable for %s: %s", zip_code, exc)
        return None
    _sun[zip_code] = (time.monotonic(), (sunrise, sunset))
    return sunrise, sunset


# WMO weather codes (Open-Meteo) in words a child knows.
_CONDITIONS = [
    ((0,), "clear"),
    ((1,), "mostly clear"),
    ((2,), "partly cloudy"),
    ((3,), "cloudy"),
    ((45, 48), "foggy"),
    ((51, 53, 55, 56, 57), "drizzly"),
    ((61, 63, 65, 66, 67, 80, 81, 82), "rainy"),
    ((71, 73, 75, 77, 85, 86), "snowy"),
    ((95, 96, 99), "stormy"),
]


def condition(code: int) -> str:
    return next((words for codes, words in _CONDITIONS if code in codes), "cloudy")


@dataclass(frozen=True)
class Weather:
    temp_f: float
    humidity: float  # relative humidity, %
    code: int  # WMO weather code
    condition: str  # e.g. "partly cloudy"


async def weather(zip_code: str) -> Weather | None:
    """The current outdoor weather at the ZIP code."""
    cached = _weather.get(zip_code)
    if cached and time.monotonic() - cached[0] < WEATHER_CACHE_SECONDS:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            latitude, longitude = await _place(client, zip_code)
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,relative_humidity_2m,weather_code",
                    "temperature_unit": "fahrenheit",
                    "timezone": "auto",
                },
            )
            response.raise_for_status()
            now = response.json()["current"]
            code = int(now["weather_code"])
            result = Weather(
                float(now["temperature_2m"]), float(now["relative_humidity_2m"]), code, condition(code)
            )
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        log.warning("Weather unavailable for %s: %s", zip_code, exc)
        return None
    _weather[zip_code] = (time.monotonic(), result)
    return result
