"""Place lookups and outdoor air quality, from free APIs that need no key.

- us_aqi(zip): ZIP -> latitude/longitude via api.zippopotam.us, then the current US AQI
  from Open-Meteo's air-quality API (cached for 30 minutes).
- zip_for(lat, lon): the browser's location -> a US ZIP code via OpenStreetMap Nominatim.

Any failure returns None.
"""

import logging
import time

import httpx

log = logging.getLogger(__name__)

AQI_CACHE_SECONDS = 30 * 60
_places: dict[str, tuple[float, float]] = {}
_aqi: dict[str, tuple[float, float]] = {}  # zip -> (fetched_at, aqi)


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
