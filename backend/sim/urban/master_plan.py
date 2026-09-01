"""
Radial master plan — city grows from centre outward.

Specification section 1 and 33: districts are placed in concentric rings with
industry downwind and farms on the periphery.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..rng import Rng
from ..world.plans import DistrictPlan
from .zones import CityZone, district_for, spec_for, zone_for_distance


@dataclass(frozen=True, slots=True)
class MasterPlan:
    """The city's spatial blueprint."""

    centre_x: int
    centre_y: int
    width: int
    height: int
    districts: tuple[DistrictPlan, ...]


def plan_initial_city(width: int, height: int, rng: Rng) -> MasterPlan:
    """
    Lays out the founding districts per specification section 43.

    Returns district rectangles with zone metadata embedded via the extended
    DistrictPlan fields (zone, density).
    """
    cx, cy = width // 2, height // 2
    radius = min(width, height) // 2
    plans: list[DistrictPlan] = []

    # Fixed anchors for special zones that must not be purely radial.
    placements: list[tuple[CityZone, float, float, float, float]] = [
        (CityZone.CITY_CENTER, 0.43, 0.43, 0.14, 0.14),
        (CityZone.GOVERNMENT, 0.40, 0.38, 0.20, 0.08),
        (CityZone.PARK, 0.30, 0.06, 0.16, 0.12),
        (CityZone.COMMERCIAL, 0.28, 0.58, 0.18, 0.14),
        (CityZone.BUSINESS, 0.58, 0.28, 0.16, 0.18),
        (CityZone.MEDIUM_DENSITY_RESIDENTIAL, 0.06, 0.06, 0.30, 0.34),
        (CityZone.LOW_DENSITY_RESIDENTIAL, 0.06, 0.58, 0.20, 0.22),
        (CityZone.EDUCATION, 0.08, 0.72, 0.16, 0.16),
        (CityZone.HEALTHCARE, 0.40, 0.06, 0.14, 0.14),
        (CityZone.INDUSTRIAL, 0.60, 0.06, 0.20, 0.20),
        (CityZone.LOGISTICS, 0.72, 0.28, 0.18, 0.16),
        (CityZone.AGRICULTURE, 0.42, 0.72, 0.28, 0.22),
        (CityZone.RECREATION, 0.06, 0.72, 0.20, 0.20),
    ]

    for zone, fx, fy, fw, fh in placements:
        w = max(8, int(width * fw))
        h = max(8, int(height * fh))
        x = max(0, min(width - w, int(width * fx)))
        y = max(0, min(height - h, int(height * fy)))
        spec = spec_for(zone)
        plans.append(
            DistrictPlan(
                district=district_for(zone),
                zone=zone,
                x=x,
                y=y,
                width=w,
                height=h,
                density=spec.building_density,
                road_density=spec.road_density,
            )
        )

    # Suburban ring on the outer edge (asymmetric so it reads natural).
    outer = max(12, int(radius * 0.38))
    plans.append(
        DistrictPlan(
            district=district_for(CityZone.SUBURBAN),
            zone=CityZone.SUBURBAN,
            x=max(0, cx - outer),
            y=max(0, cy - outer),
            width=min(width, outer * 2),
            height=min(height, outer * 2),
            density=spec_for(CityZone.SUBURBAN).building_density,
            road_density=spec_for(CityZone.SUBURBAN).road_density,
        )
    )

    return MasterPlan(cx, cy, width, height, tuple(plans))


def pick_expansion_zone(
    *,
    centre_x: int,
    centre_y: int,
    plot_x: int,
    plot_y: int,
    map_width: int,
    map_height: int,
    preferred: CityZone | None = None,
) -> CityZone:
    """Zone type for a newly opened block based on its distance from centre."""
    if preferred is not None:
        return preferred
    dx = plot_x + 12 - centre_x
    dy = plot_y + 12 - centre_y
    dist = (dx * dx + dy * dy) ** 0.5
    max_dist = (map_width ** 2 + map_height ** 2) ** 0.5 / 2
    return zone_for_distance(min(1.0, dist / max(1.0, max_dist)))
