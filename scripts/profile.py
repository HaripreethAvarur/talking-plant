"""Apply a validated plant profile to the DB. Restart backend to load new thresholds."""

import argparse
from pathlib import Path

from backend.config import Settings
from backend.database.store import Store
from shared.contracts import PlantProfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    profile = PlantProfile.model_validate_json(args.file.read_text())
    store = Store(Settings())
    if store.engine is None:
        raise SystemExit("Set DATABASE_URL; without a database, change PROFILE_PATH and restart instead.")
    try:
        store.start(profile)
        store.update_profile(profile)
    except Exception as exc:
        raise SystemExit(f"Profile update failed ({type(exc).__name__}); check DB configuration.") from None
    finally:
        store.close()
    print(f"Updated {profile.plant_id}; restart backend to load the profile.")


if __name__ == "__main__":
    main()
