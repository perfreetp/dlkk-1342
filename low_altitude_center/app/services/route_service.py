import json
import math
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import Route
from ..schemas.schemas import RouteCreate, RouteValidateResult

EARTH_RADIUS_KM = 6371.0
AVERAGE_SPEED_MPS = 5.0


def _haversine(lat1, lon1, lat2, lon2) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_KM * c


def _calc_total_distance(waypoints) -> float:
    total = 0.0
    for i in range(len(waypoints) - 1):
        total += _haversine(
            waypoints[i].latitude, waypoints[i].longitude,
            waypoints[i + 1].latitude, waypoints[i + 1].longitude,
        )
    return total


def _calc_estimated_duration(waypoints, total_distance_km) -> float:
    hover_total = sum(wp.hover_seconds for wp in waypoints)
    travel_seconds = total_distance_km * 1000.0 / AVERAGE_SPEED_MPS
    return travel_seconds + hover_total


def _is_in_restricted_zone(lat: float, lon: float) -> bool:
    return 39.9 <= lat <= 40.0 and 116.3 <= lon <= 116.4


async def create_route(db: AsyncSession, route_data: RouteCreate) -> Route:
    waypoints_list = [wp.model_dump() for wp in route_data.waypoints]
    total_distance = _calc_total_distance(route_data.waypoints)
    estimated_duration = _calc_estimated_duration(route_data.waypoints, total_distance)

    route = Route(
        name=route_data.name,
        description=route_data.description,
        waypoints_json=json.dumps(waypoints_list),
        max_altitude=route_data.max_altitude,
        min_altitude=route_data.min_altitude,
        area_polygon_json=json.dumps(route_data.area_polygon) if route_data.area_polygon else "",
        total_distance=total_distance,
        estimated_duration=estimated_duration,
    )
    db.add(route)
    await db.commit()
    await db.refresh(route)
    return route


async def get_route(db: AsyncSession, route_id: int) -> Optional[Route]:
    result = await db.execute(select(Route).where(Route.id == route_id))
    return result.scalars().first()


async def list_routes(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    count_query = select(func.count()).select_from(Route)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    query = select(Route).order_by(Route.id.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def validate_route(db: AsyncSession, route_id: int) -> RouteValidateResult:
    route = await get_route(db, route_id)
    if route is None:
        return RouteValidateResult(is_valid=False, errors=["Route not found"])

    errors: list[str] = []
    waypoints = json.loads(route.waypoints_json)

    if route.max_altitude > 120.0:
        errors.append("Max altitude exceeds regulation limit of 120.0m")
    if route.min_altitude < 0:
        errors.append("Min altitude is below 0")

    for i, wp in enumerate(waypoints):
        if _is_in_restricted_zone(wp["latitude"], wp["longitude"]):
            errors.append(
                f"Waypoint {i} ({wp['latitude']}, {wp['longitude']}) is in a restricted area"
            )

    is_valid = len(errors) == 0
    route.validation_status = "valid" if is_valid else "invalid"
    route.validation_errors_json = json.dumps(errors)
    await db.commit()
    await db.refresh(route)

    return RouteValidateResult(is_valid=is_valid, errors=errors)


async def delete_route(db: AsyncSession, route_id: int) -> bool:
    route = await get_route(db, route_id)
    if route is None:
        return False
    await db.delete(route)
    await db.commit()
    return True
