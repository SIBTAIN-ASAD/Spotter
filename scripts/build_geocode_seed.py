"""Build geocode seed JSON from GeoNames US data."""

from __future__ import annotations

import csv
import json
import zipfile
from io import TextIOWrapper
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "fuel-prices-for-be-assessment.csv"
OUTPUT_PATH = ROOT / "data" / "geocode_seed.json"
GEONAMES_URL = "https://download.geonames.org/export/dump/US.zip"
GEONAMES_ZIP = ROOT / "data" / "US.zip"


def load_geonames_places() -> dict[tuple[str, str], tuple[float, float]]:
    if not GEONAMES_ZIP.exists():
        urlretrieve(GEONAMES_URL, GEONAMES_ZIP)

    places: dict[tuple[str, str], tuple[float, float]] = {}
    with zipfile.ZipFile(GEONAMES_ZIP) as archive, archive.open("US.txt") as raw:
        handle = TextIOWrapper(raw, encoding="utf-8")
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 11:
                continue
            name = parts[1]
            latitude = float(parts[4])
            longitude = float(parts[5])
            feature_class = parts[6]
            state = parts[10]
            if feature_class != "P" or not state:
                continue

            key = (name.upper(), state.upper())
            places.setdefault(key, (latitude, longitude))

    return places


def unique_city_states(csv_path: Path) -> list[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            city = " ".join(row["City"].split())
            state = row["State"].strip().upper()
            pairs.add((city, state))
    return sorted(pairs)


def main() -> None:
    geonames = load_geonames_places()
    pairs = unique_city_states(CSV_PATH)
    seed: dict[str, dict[str, list[float]]] = {}
    matched = 0
    unmatched: list[tuple[str, str]] = []

    for city, state in pairs:
        coords = geonames.get((city.upper(), state))
        if coords is None:
            unmatched.append((city, state))
            continue
        seed.setdefault(state, {})[city.upper()] = [coords[0], coords[1]]
        matched += 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(seed, handle)

    print(f"Matched {matched}/{len(pairs)} city/state pairs.")
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Unmatched: {len(unmatched)}")


if __name__ == "__main__":
    main()
