"""Load fuel stations from the assessment CSV."""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.fuel.models import FuelStation
from apps.fuel.services.geocoding import GeocodeCacheService, NominatimGeocodingClient


class Command(BaseCommand):
    help = "Load fuel stations from CSV and attach cached coordinates."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--csv-path",
            default=settings.FUEL_PRICES_CSV_PATH,
            help="Path to fuel prices CSV file.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing fuel stations before loading.",
        )
        parser.add_argument(
            "--remote-geocode",
            action="store_true",
            help="Use Nominatim for city/state pairs missing from the seed cache.",
        )

    def handle(self, *args, **options) -> None:
        csv_path = Path(options["csv_path"])
        if not csv_path.is_absolute():
            csv_path = Path(settings.BASE_DIR) / csv_path

        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        stations = self._read_csv(csv_path)
        cache_service = GeocodeCacheService(
            remote_client=NominatimGeocodingClient() if options["remote_geocode"] else None,
        )

        created = 0
        skipped_no_coords = 0
        coordinate_cache: dict[tuple[str, str], tuple[float, float] | None] = {}

        with transaction.atomic():
            if options["clear"]:
                deleted_count, _ = FuelStation.objects.all().delete()
                self.stdout.write(
                    self.style.WARNING(f"Deleted {deleted_count} existing fuel stations.")
                )

            for row in stations:
                location_key = (row["city"], row["state"])
                if location_key not in coordinate_cache:
                    coords = cache_service.get_city_state_coordinates(
                        row["city"],
                        row["state"],
                        allow_remote=options["remote_geocode"],
                    )
                    coordinate_cache[location_key] = (
                        (coords.latitude, coords.longitude) if coords else None
                    )

                coords_tuple = coordinate_cache[location_key]
                if coords_tuple is None:
                    skipped_no_coords += 1
                    continue

                FuelStation.objects.update_or_create(
                    opis_id=row["opis_id"],
                    name=row["name"],
                    address=row["address"],
                    city=row["city"],
                    state=row["state"],
                    defaults={
                        "rack_id": row["rack_id"],
                        "retail_price": row["retail_price"],
                        "latitude": coords_tuple[0],
                        "longitude": coords_tuple[1],
                    },
                )
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Loaded/updated "
                f"{created} fuel stations. Skipped {skipped_no_coords} without coordinates."
            )
        )

    def _read_csv(self, csv_path: Path) -> list[dict]:
        grouped: dict[tuple[str, str, str, str, str], dict] = {}

        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    price = Decimal(str(row["Retail Price"]).strip())
                except (InvalidOperation, KeyError, TypeError) as exc:
                    raise CommandError(f"Invalid retail price in row: {row}") from exc

                city = " ".join(row["City"].split())
                state = row["State"].strip().upper()
                dedupe_key = (
                    row["OPIS Truckstop ID"].strip(),
                    row["Truckstop Name"].strip(),
                    row["Address"].strip(),
                    city,
                    state,
                )

                existing = grouped.get(dedupe_key)
                if existing is None or price < existing["retail_price"]:
                    grouped[dedupe_key] = {
                        "opis_id": dedupe_key[0],
                        "name": dedupe_key[1],
                        "address": dedupe_key[2],
                        "city": city,
                        "state": state,
                        "rack_id": row.get("Rack ID", "").strip(),
                        "retail_price": price,
                    }

        return list(grouped.values())
