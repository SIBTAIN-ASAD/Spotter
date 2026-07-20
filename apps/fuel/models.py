"""Fuel station and geocode cache models."""

from django.db import models


class GeocodeCache(models.Model):
    city = models.CharField(max_length=128)
    state = models.CharField(max_length=2, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    source = models.CharField(max_length=32, default="nominatim")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["city", "state"], name="uniq_geocode_city_state"),
        ]
        indexes = [
            models.Index(fields=["state", "city"]),
        ]

    def __str__(self) -> str:
        return f"{self.city}, {self.state}"


class FuelStation(models.Model):
    opis_id = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=128, db_index=True)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.CharField(max_length=32, blank=True)
    retail_price = models.DecimalField(max_digits=8, decimal_places=4)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["state", "retail_price"]),
            models.Index(fields=["latitude", "longitude"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state})"
