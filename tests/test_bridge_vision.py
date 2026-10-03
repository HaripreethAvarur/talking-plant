import json
from pathlib import Path

import httpx
import pytest

from backend.sensors.bridge import publish, replay_rows, validate_backend_url
from backend.sensors.calibration import Calibration
from backend.sensors.freewili_adapter import FreeWiliAdapter, HardwareConfig, MeasurementUnavailable
from backend.vision.observe import ColorBaseline, capture
from shared.contracts import SensorReading, Status


def test_calibration_persists_in_both_directions(tmp_path):
    for dry, wet in ((1000, 200), (200, 1000)):
        c = Calibration(dry_raw=dry, wet_raw=wet, sensor_model="test", device_id="test")
        assert c.convert(dry).relative_percent == 0
        assert c.convert(wet).relative_percent == 100
        assert c.convert(600).relative_percent == 50
        path = tmp_path / "calibration.json"
        c.save(path)
        assert Calibration.model_validate_json(path.read_text()) == c


def test_fixture_validation_and_rebase():
    path = Path("shared/fixtures/dry-to-watered.jsonl")
    originals = [SensorReading.model_validate_json(line) for line in path.read_text().splitlines()]
    rows = replay_rows(path, "plant-1")
    assert len(rows) == 24
    assert rows[-1].timestamp - rows[0].timestamp == originals[-1].timestamp - originals[0].timestamp
    assert rows[0].event_id != originals[0].event_id
    assert rows[0].source.value == "replay"


async def test_http_retry_preserves_event_id(reading):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(503 if len(requests) < 2 else 200, json={"status": "accepted"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://localhost"
    ) as client:
        assert await publish(client, "/api/v1/sensor-readings", reading(0)) == {"status": "accepted"}
    assert requests[0] == requests[1]


def test_remote_url_validation():
    for url in ("http://localhost.evil.test", "http://remote.test", "https://user:secret@host"):
        with pytest.raises(ValueError):
            validate_backend_url(url)
    validate_backend_url("https://plant.example")


def test_verified_adapter_lifecycle(monkeypatch):
    calls = []

    class Result:
        def expect(self, message):
            return None

    class Device:
        def __str__(self):
            return "device-A"

        def open(self, timeout_sec):
            calls.append("open")
            return Result()

        def close(self):
            calls.append("close")

    monkeypatch.setattr(FreeWiliAdapter, "candidates", staticmethod(lambda: [Device()]))
    adapter = FreeWiliAdapter(HardwareConfig("device-A", "test-board", "test-firmware"))
    adapter.connect()
    with pytest.raises(MeasurementUnavailable):
        adapter.read_moisture()
    with pytest.raises(MeasurementUnavailable):
        adapter.read_light()
    adapter.cleanup()
    assert calls == ["open", "close"]


def test_missing_image_or_camera_does_not_crash(monkeypatch):
    assert capture(image_path=Path("/nonexistent/image.jpg"), region=(0, 0, 100, 100)).status == Status.error
    cv2 = pytest.importorskip("cv2")

    class MissingCamera:
        def isOpened(self):
            return False

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", lambda index: MissingCamera())
    assert capture(region=(0, 0, 100, 100)).status == Status.error


def test_color_region_and_unusable_images(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image[:] = (0, 255, 255)
    observation = ColorBaseline().observe(image, (0, 0, 100, 100))
    assert observation.yellow_proportion == 1
    assert observation.brown_proportion == 0
    path = tmp_path / "yellow.png"
    cv2.imwrite(str(path), image)
    assert capture(image_path=path, region=(0, 0, 100, 100)).yellow_proportion == 1
    assert ColorBaseline().observe(image, (99, 99, 100, 100)).status == Status.error
    assert ColorBaseline().observe(np.zeros_like(image), (0, 0, 100, 100)).status == Status.error
