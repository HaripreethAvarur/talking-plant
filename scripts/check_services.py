"""Check every external connection live and print the results.

    python -m scripts.check_services          # uses about 10 ElevenLabs characters

Neon, ElevenLabs (account, voice, speech-to-text), ASI:One, the Plant Care Agent
(local process + Agentverse Almanac), Ollama, the air-quality APIs, and the running backend.
"""

import asyncio
import time

import httpx

from backend import air
from backend.config import get_settings
from backend.conversation.scripted import cacheable_lines
from backend.database.store import Store
from backend.speech import stt, tts

OK, FAIL, WARN = "PASS", "FAIL", "WARN"
results: list[tuple[str, str, str]] = []


def report(name, status, detail):
    results.append((name, status, detail))
    print(f"[{status}] {name:<28} {detail}", flush=True)


def timed(started):
    return f"{time.perf_counter() - started:.2f}s"


async def check_neon(settings):
    started = time.perf_counter()
    try:
        store = Store(settings)
        from sqlalchemy import text

        with store.engine.connect() as conn:
            version = conn.execute(text("show server_version")).scalar()
        store.close()
        report("Neon Postgres", OK, f"server {version}, connected in {timed(started)}")
    except Exception as exc:
        report("Neon Postgres", FAIL, f"{type(exc).__name__}: {exc}"[:160])


async def check_elevenlabs(settings):
    key = settings.elevenlabs_api_key.get_secret_value()
    if not key:
        return report("ElevenLabs", FAIL, "ELEVENLABS_API_KEY is empty")
    headers = {"xi-api-key": key}
    async with httpx.AsyncClient(
        base_url=settings.elevenlabs_base_url, timeout=30, headers=headers
    ) as client:
        r = await client.get("/v1/user/subscription")
        if r.status_code != 200:
            return report("ElevenLabs account", FAIL, f"HTTP {r.status_code}: {r.text[:120]}")
        sub = r.json()
        report(
            "ElevenLabs account",
            OK,
            f"tier {sub['tier']}, {sub['character_count']}/{sub['character_limit']} characters used this month",
        )
        r = await client.get(f"/v1/voices/{settings.elevenlabs_voice_id}")
        name = r.json().get("name", "?") if r.status_code == 200 else f"HTTP {r.status_code}"
        report(
            "ElevenLabs voice",
            OK if r.status_code == 200 else FAIL,
            f"{settings.elevenlabs_voice_id} = {name}",
        )

    started = time.perf_counter()
    text = "Hello friend!"
    path = tts.cache_path(text)
    path.unlink(missing_ok=True)  # force a real request
    audio = await tts.synthesize(text)
    if not audio.audio_url:
        return report("ElevenLabs text-to-speech", FAIL, "no audio returned (see backend log)")
    report(
        "ElevenLabs text-to-speech", OK, f"'{text}' -> {path.stat().st_size} bytes MP3 in {timed(started)}"
    )

    started = time.perf_counter()
    clip = tts.cache_path(cacheable_lines()[0])
    sample = clip if clip.exists() else path
    try:
        heard = await stt.transcribe(sample.read_bytes(), "audio/mpeg")
        report("ElevenLabs speech-to-text", OK, f"heard '{heard.text}' in {timed(started)}")
    except stt.SttUnavailable as exc:
        report("ElevenLabs speech-to-text", FAIL, str(exc))


async def check_asi(settings):
    key = settings.asi_api_key.get_secret_value()
    if not key:
        return report("ASI:One", FAIL, "ASI_API_KEY is empty")
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{settings.asi_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": settings.asi_model,
                "messages": [
                    {"role": "user", "content": "You are a plant. Say hello to a child in 6 words."}
                ],
                "max_tokens": 30,
            },
        )
    if r.status_code != 200:
        return report("ASI:One", FAIL, f"HTTP {r.status_code}: {r.text[:120]}")
    body = r.json()
    reply = body["choices"][0]["message"]["content"].strip()
    tokens = body.get("usage", {}).get("total_tokens", "?")
    report("ASI:One", OK, f"{settings.asi_model} replied '{reply}' ({tokens} tokens, {timed(started)})")


async def check_agent(settings):
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(f"http://127.0.0.1:{settings.agent_port}/agent_info")
            info = r.json()
            address = info.get("address", "")
            report("Plant Care Agent (local)", OK, f"running on :{settings.agent_port}, address {address}")
        except (httpx.HTTPError, ValueError):
            return report("Plant Care Agent (local)", FAIL, "not running: python -m backend.agent.chat_agent")
        r = await client.get(f"https://agentverse.ai/v1/almanac/agents/{address}")
        if r.status_code == 200:
            data = r.json()
            protocols = len(data.get("protocols", []))
            endpoints = ", ".join(e.get("url", "") for e in data.get("endpoints", [])) or "-"
            report(
                "Agentverse Almanac",
                OK,
                f"registered, status {data.get('status', '?')}, {protocols} protocol(s), endpoint {endpoints}",
            )
        else:
            report("Agentverse Almanac", WARN, f"HTTP {r.status_code}: {r.text[:120]}")


async def check_ollama(settings):
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            version = (await client.get(f"{settings.ollama_url}/api/version")).json()["version"]
            models = [
                m["name"] for m in (await client.get(f"{settings.ollama_url}/api/tags")).json()["models"]
            ]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return report("Ollama", FAIL, f"not reachable ({type(exc).__name__})")
    wanted = settings.ollama_model
    has = any(m.split(":")[0] == wanted.split(":")[0] for m in models)
    report("Ollama", OK if has else WARN, f"v{version}, models {models}, using '{wanted}'")


async def check_air(settings):
    store = Store(settings)
    from sqlalchemy import select

    from backend.database.schema import plants

    with store.engine.connect() as conn:
        zip_code = conn.execute(select(plants.c.location)).scalar() or "48105"
    store.close()
    started = time.perf_counter()
    aqi = await air.us_aqi(zip_code)
    report(
        "Air quality (Open-Meteo)",
        OK if aqi is not None else FAIL,
        f"ZIP {zip_code}: US AQI {aqi} ({timed(started)})",
    )


async def check_backend(settings):
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            ready = (await client.get(f"http://127.0.0.1:{settings.port}/ready")).json()
            health = (await client.get("http://127.0.0.1:5173/api/health")).json()
        except (httpx.HTTPError, ValueError) as exc:
            return report("Backend + UI", FAIL, f"not reachable ({type(exc).__name__})")
    report(
        "Backend + UI",
        OK,
        f"db {ready['database']}, plant '{health['plant']['name']}', stt {health['stt']}, "
        f"tts {health['tts']}, llm {health['llm']}",
    )


async def main():
    settings = get_settings()
    print(f"Checking connections at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    for check in (
        check_neon,
        check_elevenlabs,
        check_asi,
        check_agent,
        check_ollama,
        check_air,
        check_backend,
    ):
        try:
            await check(settings)
        except Exception as exc:
            report(check.__name__.removeprefix("check_"), FAIL, f"{type(exc).__name__}: {exc}"[:160])
    failed = [name for name, status, _ in results if status == FAIL]
    print(
        f"\n{len(results) - len(failed)}/{len(results)} checks passed"
        + (f"; failed: {failed}" if failed else "")
    )


if __name__ == "__main__":
    asyncio.run(main())
