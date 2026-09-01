"""
City zoning — density, road density and building rules per zone.

`CityZone` is the urban-planning vocabulary. `District` (in tiles.py) is what
the construction pipeline reads; each zone maps to one district so existing
buildings and saves keep working.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..world.tiles import District


class CityZone(StrEnum):
    """Specification section 2 — urban zone types."""

    CITY_CENTER = "city_center"
    GOVERNMENT = "government"
    BUSINESS = "business"
    COMMERCIAL = "commercial"
    HIGH_DENSITY_RESIDENTIAL = "high_density_residential"
    MEDIUM_DENSITY_RESIDENTIAL = "medium_density_residential"
    LOW_DENSITY_RESIDENTIAL = "low_density_residential"
    INDUSTRIAL = "industrial"
    LOGISTICS = "logistics"
    EDUCATION = "education"
    HEALTHCARE = "healthcare"
    RECREATION = "recreation"
    PARK = "park"
    SPORT = "sport"
    AGRICULTURE = "agriculture"
    SUBURBAN = "suburban"
    FOREST = "forest"
    WATER = "water"
    INFRASTRUCTURE = "infrastructure"


#: Maps each zone to the district enum the construction system understands.
ZONE_TO_DISTRICT: dict[CityZone, District] = {
    CityZone.CITY_CENTER: District.CITY_CENTER,
    CityZone.GOVERNMENT: District.CITY_CENTER,
    CityZone.BUSINESS: District.BUSINESS,
    CityZone.COMMERCIAL: District.SHOPPING,
    CityZone.HIGH_DENSITY_RESIDENTIAL: District.RESIDENTIAL,
    CityZone.MEDIUM_DENSITY_RESIDENTIAL: District.RESIDENTIAL,
    CityZone.LOW_DENSITY_RESIDENTIAL: District.RESIDENTIAL,
    CityZone.INDUSTRIAL: District.INDUSTRIAL,
    CityZone.LOGISTICS: District.INDUSTRIAL,
    CityZone.EDUCATION: District.SCHOOL,
    CityZone.HEALTHCARE: District.HOSPITAL,
    CityZone.RECREATION: District.PARK,
    CityZone.PARK: District.PARK,
    CityZone.SPORT: District.PARK,
    CityZone.AGRICULTURE: District.FARM,
    CityZone.SUBURBAN: District.RESIDENTIAL,
    CityZone.FOREST: District.UNZONED,
    CityZone.WATER: District.UNZONED,
    CityZone.INFRASTRUCTURE: District.INDUSTRIAL,
}


LABELS: dict[CityZone, str] = {
    CityZone.CITY_CENTER: "shahar markazi",
    CityZone.GOVERNMENT: "davlat hududi",
    CityZone.BUSINESS: "biznes hududi",
    CityZone.COMMERCIAL: "savdo hududi",
    CityZone.HIGH_DENSITY_RESIDENTIAL: "yuqori zichlikli turar-joy",
    CityZone.MEDIUM_DENSITY_RESIDENTIAL: "o'rta zichlikli turar-joy",
    CityZone.LOW_DENSITY_RESIDENTIAL: "past zichlikli turar-joy",
    CityZone.INDUSTRIAL: "sanoat hududi",
    CityZone.LOGISTICS: "logistika hududi",
    CityZone.EDUCATION: "ta'lim hududi",
    CityZone.HEALTHCARE: "sog'liqni saqlash hududi",
    CityZone.RECREATION: "dam olish hududi",
    CityZone.PARK: "bog'",
    CityZone.SPORT: "sport hududi",
    CityZone.AGRICULTURE: "qishloq xo'jaligi",
    CityZone.SUBURBAN: "shahar cheti",
    CityZone.FOREST: "o'rmon",
    CityZone.WATER: "suv",
    CityZone.INFRASTRUCTURE: "infratuzilma",
}


@dataclass(frozen=True, slots=True)
class ZoneSpec:
    """Density and skyline rules for one zone type."""

    zone: CityZone
    building_density: float  # 0–1, share of buildable tiles that may hold buildings
    road_density: float  # 0–1, how much of the zone is road network
    min_floors: int
    max_floors: int
    green_ratio: float  # minimum green space share
    block_size: int  # metres/tiles between major roads


SPECS: dict[CityZone, ZoneSpec] = {
    CityZone.CITY_CENTER: ZoneSpec(CityZone.CITY_CENTER, 0.55, 0.22, 8, 50, 0.15, 10),
    CityZone.GOVERNMENT: ZoneSpec(CityZone.GOVERNMENT, 0.35, 0.18, 2, 15, 0.30, 14),
    CityZone.BUSINESS: ZoneSpec(CityZone.BUSINESS, 0.50, 0.20, 10, 30, 0.12, 12),
    CityZone.COMMERCIAL: ZoneSpec(CityZone.COMMERCIAL, 0.45, 0.24, 1, 8, 0.10, 10),
    CityZone.HIGH_DENSITY_RESIDENTIAL: ZoneSpec(
        CityZone.HIGH_DENSITY_RESIDENTIAL, 0.48, 0.20, 5, 20, 0.18, 12
    ),
    CityZone.MEDIUM_DENSITY_RESIDENTIAL: ZoneSpec(
        CityZone.MEDIUM_DENSITY_RESIDENTIAL, 0.38, 0.16, 2, 8, 0.22, 14
    ),
    CityZone.LOW_DENSITY_RESIDENTIAL: ZoneSpec(
        CityZone.LOW_DENSITY_RESIDENTIAL, 0.28, 0.12, 1, 3, 0.30, 16
    ),
    CityZone.INDUSTRIAL: ZoneSpec(CityZone.INDUSTRIAL, 0.40, 0.18, 1, 6, 0.08, 16),
    CityZone.LOGISTICS: ZoneSpec(CityZone.LOGISTICS, 0.35, 0.22, 1, 4, 0.05, 14),
    CityZone.EDUCATION: ZoneSpec(CityZone.EDUCATION, 0.32, 0.14, 1, 5, 0.25, 14),
    CityZone.HEALTHCARE: ZoneSpec(CityZone.HEALTHCARE, 0.30, 0.16, 2, 10, 0.20, 14),
    CityZone.RECREATION: ZoneSpec(CityZone.RECREATION, 0.15, 0.10, 1, 2, 0.60, 20),
    CityZone.PARK: ZoneSpec(CityZone.PARK, 0.08, 0.08, 1, 1, 0.75, 20),
    CityZone.SPORT: ZoneSpec(CityZone.SPORT, 0.25, 0.14, 1, 4, 0.35, 16),
    CityZone.AGRICULTURE: ZoneSpec(CityZone.AGRICULTURE, 0.20, 0.10, 1, 2, 0.40, 20),
    CityZone.SUBURBAN: ZoneSpec(CityZone.SUBURBAN, 0.22, 0.10, 1, 3, 0.35, 18),
    CityZone.FOREST: ZoneSpec(CityZone.FOREST, 0.0, 0.05, 0, 0, 0.95, 24),
    CityZone.WATER: ZoneSpec(CityZone.WATER, 0.0, 0.0, 0, 0, 0.0, 0),
    CityZone.INFRASTRUCTURE: ZoneSpec(CityZone.INFRASTRUCTURE, 0.30, 0.25, 1, 3, 0.05, 16),
}


def spec_for(zone: CityZone) -> ZoneSpec:
    return SPECS[zone]


def district_for(zone: CityZone) -> District:
    return ZONE_TO_DISTRICT[zone]


def label_for(zone: CityZone) -> str:
    return LABELS.get(zone, zone.value)


def zone_for_distance(normalized_distance: float) -> CityZone:
    """
    Picks a zone from radial distance to city centre (0 = centre, 1 = edge).

    Implements the master-plan ring structure from specification section 1.
    """
    if normalized_distance < 0.08:
        return CityZone.CITY_CENTER
    if normalized_distance < 0.12:
        return CityZone.GOVERNMENT
    if normalized_distance < 0.20:
        return CityZone.COMMERCIAL
    if normalized_distance < 0.28:
        return CityZone.BUSINESS
    if normalized_distance < 0.42:
        return CityZone.MEDIUM_DENSITY_RESIDENTIAL
    if normalized_distance < 0.55:
        return CityZone.LOW_DENSITY_RESIDENTIAL
    if normalized_distance < 0.62:
        return CityZone.EDUCATION
    if normalized_distance < 0.68:
        return CityZone.HEALTHCARE
    if normalized_distance < 0.75:
        return CityZone.RECREATION
    if normalized_distance < 0.82:
        return CityZone.INDUSTRIAL
    if normalized_distance < 0.90:
        return CityZone.LOGISTICS
    if normalized_distance < 0.95:
        return CityZone.AGRICULTURE
    return CityZone.SUBURBAN
