from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from ..core.enums import TaskStatus, AirspaceStatus, DeviceStatus, FlightEventType, AlertType, AlertSeverity, ReportType, MaintenanceType


class TaskCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: str = ""
    task_type: str = "inspection"
    pilot_id: Optional[int] = None
    drone_id: Optional[int] = None
    route_id: Optional[int] = None
    airspace_id: Optional[int] = None
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    parent_task_id: Optional[int] = None


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    pilot_id: Optional[int] = None
    drone_id: Optional[int] = None
    route_id: Optional[int] = None
    airspace_id: Optional[int] = None
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    result_summary: Optional[str] = None


class TaskOut(BaseModel):
    id: int
    name: str
    description: str
    status: str
    task_type: str
    pilot_id: Optional[int]
    drone_id: Optional[int]
    route_id: Optional[int]
    airspace_id: Optional[int]
    planned_start: Optional[datetime]
    planned_end: Optional[datetime]
    actual_start: Optional[datetime]
    actual_end: Optional[datetime]
    parent_task_id: Optional[int]
    result_summary: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskMergeRequest(BaseModel):
    task_ids: List[int] = Field(..., min_length=2)
    merged_name: str = Field(..., max_length=200)
    merged_description: str = ""


class Waypoint(BaseModel):
    latitude: float
    longitude: float
    altitude: float
    speed: float = 5.0
    hover_seconds: float = 0.0


class RouteCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: str = ""
    waypoints: List[Waypoint] = Field(..., min_length=2)
    max_altitude: float = 120.0
    min_altitude: float = 0.0
    area_polygon: Optional[List[List[float]]] = None


class RouteValidateResult(BaseModel):
    is_valid: bool
    errors: List[str]


class RouteOut(BaseModel):
    id: int
    name: str
    description: str
    waypoints_json: str
    max_altitude: float
    min_altitude: float
    area_polygon_json: str
    total_distance: float
    estimated_duration: float
    validation_status: str
    validation_errors_json: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AirspaceCreate(BaseModel):
    name: str = Field(..., max_length=200)
    area: List[List[float]] = Field(..., min_length=3)
    floor_altitude: float = 0.0
    ceiling_altitude: float = 120.0
    applicant: str = ""
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


class AirspaceApprove(BaseModel):
    approver: str
    approved: bool
    reject_reason: str = ""


class AirspaceOut(BaseModel):
    id: int
    name: str
    area_json: str
    floor_altitude: float
    ceiling_altitude: float
    status: str
    applicant: str
    apply_time: Optional[datetime]
    approve_time: Optional[datetime]
    approver: str
    reject_reason: str
    valid_from: Optional[datetime]
    valid_to: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeviceCreate(BaseModel):
    name: str = Field(..., max_length=200)
    device_type: str = Field(..., max_length=50)
    model: str = ""
    serial_number: str = Field(..., max_length=100)
    license_number: str = ""
    license_expiry: Optional[datetime] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    license_number: Optional[str] = None
    license_expiry: Optional[datetime] = None


class DeviceOut(BaseModel):
    id: int
    name: str
    device_type: str
    model: str
    serial_number: str
    status: str
    license_number: str
    license_expiry: Optional[datetime]
    last_maintenance: Optional[datetime]
    next_maintenance: Optional[datetime]
    total_flight_hours: float
    total_flight_count: int
    current_latitude: Optional[float]
    current_longitude: Optional[float]
    current_altitude: Optional[float]
    current_battery: Optional[float]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MaintenanceRecordCreate(BaseModel):
    maintenance_type: str
    description: str = ""
    performed_by: str = ""
    next_maintenance_date: Optional[datetime] = None
    cost: float = 0.0


class MaintenanceRecordOut(BaseModel):
    id: int
    device_id: int
    maintenance_type: str
    description: str
    performed_by: str
    performed_at: datetime
    next_maintenance_date: Optional[datetime]
    cost: float

    model_config = {"from_attributes": True}


class FlightPositionCreate(BaseModel):
    device_id: int
    task_id: Optional[int] = None
    latitude: float
    longitude: float
    altitude: float
    speed: float = 0.0
    heading: float = 0.0
    battery_percent: Optional[float] = None


class FlightPositionOut(BaseModel):
    id: int
    device_id: int
    task_id: Optional[int]
    latitude: float
    longitude: float
    altitude: float
    speed: float
    heading: float
    battery_percent: Optional[float]
    timestamp: datetime

    model_config = {"from_attributes": True}


class FlightEventCreate(BaseModel):
    task_id: Optional[int] = None
    device_id: int
    event_type: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    details: dict = {}


class FlightEventOut(BaseModel):
    id: int
    task_id: Optional[int]
    device_id: int
    event_type: str
    latitude: Optional[float]
    longitude: Optional[float]
    altitude: Optional[float]
    details_json: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class AlertCreate(BaseModel):
    task_id: Optional[int] = None
    device_id: Optional[int] = None
    alert_type: str
    severity: str = "warning"
    message: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    details: dict = {}


class AlertOut(BaseModel):
    id: int
    task_id: Optional[int]
    device_id: Optional[int]
    alert_type: str
    severity: str
    message: str
    is_read: int
    latitude: Optional[float]
    longitude: Optional[float]
    details_json: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SubscriptionCreate(BaseModel):
    subscriber_id: str = Field(..., max_length=100)
    event_types: List[str] = Field(..., min_length=1)
    callback_url: str = Field(..., max_length=500)


class SubscriptionOut(BaseModel):
    subscriber_id: str
    event_types: List[str]
    callback_url: str


class MediaFileCreate(BaseModel):
    task_id: Optional[int] = None
    file_type: str
    file_url: str = Field(..., max_length=500)
    file_size: int = 0
    thumbnail_url: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    taken_at: Optional[datetime] = None


class MediaFileOut(BaseModel):
    id: int
    task_id: Optional[int]
    file_type: str
    file_url: str
    file_size: int
    thumbnail_url: str
    latitude: Optional[float]
    longitude: Optional[float]
    altitude: Optional[float]
    taken_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class AnomalyPointCreate(BaseModel):
    task_id: Optional[int] = None
    latitude: float
    longitude: float
    anomaly_type: str = ""
    description: str = ""
    severity: str = "warning"
    media_file_ids: List[int] = []


class AnomalyPointOut(BaseModel):
    id: int
    task_id: Optional[int]
    latitude: float
    longitude: float
    anomaly_type: str
    description: str
    severity: str
    media_file_ids_json: str
    is_resolved: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportQuery(BaseModel):
    report_type: str
    device_id: Optional[int] = None
    task_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class UtilizationStat(BaseModel):
    device_id: int
    device_name: str
    total_flight_hours: float
    total_flight_count: int
    utilization_rate: float
    period_start: datetime
    period_end: datetime


class TrajectoryPoint(BaseModel):
    latitude: float
    longitude: float
    altitude: float
    speed: float
    battery_percent: Optional[float]
    timestamp: datetime


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List
