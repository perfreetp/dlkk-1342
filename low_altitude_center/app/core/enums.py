from enum import Enum


class TaskStatus(str, Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AirspaceStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class FlightEventType(str, Enum):
    TAKEOFF = "takeoff"
    LANDING = "landing"
    RETURN_HOME = "return_home"
    HOVER = "hover"
    WAYPOINT_REACHED = "waypoint_reached"


class AlertType(str, Enum):
    BOUNDARY_VIOLATION = "boundary_violation"
    LOW_BATTERY = "low_battery"
    SIGNAL_LOST = "signal_lost"
    ALTITUDE_EXCEEDED = "altitude_exceeded"
    GEOFENCE_BREACH = "geofence_breach"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ReportType(str, Enum):
    DAILY = "daily"
    MONTHLY = "monthly"
    ANOMALY_LIST = "anomaly_list"
    UTILIZATION = "utilization"


class MaintenanceType(str, Enum):
    ROUTINE = "routine"
    REPAIR = "repair"
    CALIBRATION = "calibration"
