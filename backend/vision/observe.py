"""Optional native camera / image-file color observations. Images are never saved or uploaded."""

import argparse
import asyncio
import os
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from shared.contracts import LeafObservation, Source, Status


class LeafModel(Protocol):
    # TODO(MODEL): select and validate a wilting model on representative labeled leaf images,
    # implement this interface with model/version metadata, and measure errors before enabling it.
    def observe(
        self, image, region: tuple[int, int, int, int], plant_id: str, source: Source
    ) -> LeafObservation:
        """Future validated model interface: image is BGR; return observations with method/version."""
        ...


def unavailable(plant_id, source, note):
    return LeafObservation(
        plant_id=plant_id,
        source=source,
        device_id="laptop-camera" if source == Source.hardware else "image-file",
        status=Status.error,
        note=note,
    )


class ColorBaseline:
    def observe(self, image, region, plant_id="plant-1", source=Source.image_file):
        import cv2
        import numpy as np

        if image is None or image.ndim != 3 or image.shape[2] != 3:
            return unavailable(plant_id, source, "Unusable image; a BGR color image is required.")
        if region is None:
            return unavailable(plant_id, source, "Select a leaf-only region with --roi x y width height.")
        x, y, width, height = region
        if (
            min(x, y) < 0
            or min(width, height) < 8
            or x + width > image.shape[1]
            or y + height > image.shape[0]
        ):
            return unavailable(
                plant_id, source, "Region must be inside the image and at least 8 by 8 pixels."
            )
        crop = image[y : y + height, x : x + width]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hue, saturation, value = (hsv[:, :, i] for i in range(3))
        if float(np.median(value)) < 25:
            return unavailable(plant_id, source, "Region too dark for a useful color observation.")
        yellow = (hue >= 20) & (hue <= 38) & (saturation >= 60) & (value >= 70)
        brown = (hue >= 5) & (hue < 20) & (saturation >= 60) & (value >= 25) & (value <= 190)
        return LeafObservation(
            plant_id=plant_id,
            source=source,
            device_id="laptop-camera" if source == Source.hardware else "image-file",
            status=Status.ok,
            region=region,
            yellow_proportion=float(yellow.mean()),
            brown_proportion=float(brown.mean()),
        )


def capture(image_path=None, camera_index=0, region=None, plant_id="plant-1"):
    source = Source.image_file if image_path else Source.hardware
    try:
        import cv2
    except ImportError:
        return unavailable(plant_id, source, "Optional CV dependencies absent; run make install-vision.")
    try:
        if image_path:
            if not Path(image_path).is_file():
                return unavailable(plant_id, source, "Image file does not exist.")
            image = cv2.imread(str(image_path))
        else:
            camera = cv2.VideoCapture(camera_index)
            try:
                if not camera.isOpened():
                    return unavailable(
                        plant_id, source, "Camera unavailable. Check index and macOS camera permission."
                    )
                # Let auto-exposure settle; initial USB webcam frames can be black.
                ok, image = False, None
                for _ in range(5):
                    ok, image = camera.read()
                if not ok:
                    return unavailable(plant_id, source, "Camera opened but returned no frame.")
            finally:
                camera.release()
        return ColorBaseline().observe(image, region, plant_id, source)
    except Exception as exc:
        return unavailable(plant_id, source, f"Capture/analysis unavailable ({type(exc).__name__}).")


async def upload(observation):
    import httpx

    from backend.sensors.bridge import publish, validate_backend_url

    url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    validate_backend_url(url)
    token = os.getenv("INGESTION_TOKEN", "")
    async with httpx.AsyncClient(
        base_url=url, headers={"Authorization": f"Bearer {token}"} if token else {}, timeout=5
    ) as client:
        return await publish(client, "/api/v1/leaf-observations", observation)


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--camera-index", type=int, default=int(os.getenv("CAMERA_INDEX", "0")))
    parser.add_argument("--roi", type=int, nargs=4, metavar=("X", "Y", "WIDTH", "HEIGHT"), required=True)
    parser.add_argument("--plant-id", default="plant-1")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--loop", action="store_true", help="Capture repeatedly without saving images")
    parser.add_argument("--interval", type=float, default=10, help="Seconds between captures in loop mode")
    parser.add_argument("--count", type=int, default=0, help="Loop capture limit; 0 means until Ctrl-C")
    args = parser.parse_args()
    if args.interval <= 0 or args.count < 0:
        parser.error("interval must be positive and count nonnegative")
    try:
        asyncio.run(observe_loop(args))
    except KeyboardInterrupt:
        pass


async def observe_loop(args):
    count = 0
    while True:
        observation = await asyncio.to_thread(
            capture, args.image, args.camera_index, tuple(args.roi), args.plant_id
        )
        print(observation.model_dump_json(indent=2), flush=True)
        if args.publish:
            await upload(observation)
        count += 1
        if not args.loop or (args.count and count >= args.count):
            break
        await asyncio.sleep(args.interval)


if __name__ == "__main__":
    main()
