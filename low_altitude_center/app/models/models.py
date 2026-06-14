from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from ..core.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    status = Column(String(20), nullable=False, default="draft")
    task_type = Column(String(50), default="inspection")
    pilot_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    drone_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=True)
    airspace_id = Column(Integer, ForeignKey("airspaces.id"), nullable=True)
    planned_start = Column(DateTime, nullable=True)
    planned_end = Column(DateTime, nullable=True)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)
    parent_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    result_summary = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pilot = relationship("Device", foreign_keys=[pilot_id], back_populates="tasks_as_pilot")
    drone = relationship("Device", foreign_keys=[drone_id], back_populates="tasks_as_drone")
    route = relationship("Route", back_populates="tasks")
    airspace = relationship("Airspace", back_populates="tasks")
    sub_tasks = relationship("Task", backref="parent_task", remote_side=[id])
    flight_events = relationship("FlightEvent", back_populates="task")
    alerts = relationship("Alert", back_populates="task")
    media_files = relationship("MediaFile", back_populates="task")
    anomalies = relationship("AnomalyPoint", back_populates="task")


class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    waypoints_json = Column(Text, nullable=False)
    max_altitude = Column(Float, nullable=False, default=120.0)
    min_altitude = Column(Float, default=0.0)
    area_polygon_json = Column(Text, default="")
    total_distance = Column(Float, default=0.0)
    estimated_duration = Column(Float, default=0.0)
    validation_status = Column(String(20), default="pending")
    validation_errors_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tasks = relationship("Task", back_populates="route")


class Airspace(Base):
    __tablename__ = "airspaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    area_json = Column(Text, nullable=False)
    floor_altitude = Column(Float, default=0.0)
    ceiling_altitude = Column(Float, default=120.0)
    status = Column(String(20), nullable=False, default="pending")
    applicant = Column(String(100), default="")
    apply_time = Column(DateTime, nullable=True)
    approve_time = Column(DateTime, nullable=True)
    approver = Column(String(100), default="")
    reject_reason = Column(Text, default="")
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tasks = relationship("Task", back_populates="airspace")


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    device_type = Column(String(50), nullable=False)
    model = Column(String(100), default="")
    serial_number = Column(String(100), unique=True, nullable=False)
    status = Column(String(20), default="offline")
    license_number = Column(String(100), default="")
    license_expiry = Column(DateTime, nullable=True)
    last_maintenance = Column(DateTime, nullable=True)
    next_maintenance = Column(DateTime, nullable=True)
    total_flight_hours = Column(Float, default=0.0)
    total_flight_count = Column(Integer, default=0)
    current_latitude = Column(Float, nullable=True)
    current_longitude = Column(Float, nullable=True)
    current_altitude = Column(Float, nullable=True)
    current_battery = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tasks_as_pilot = relationship("Task", foreign_keys="Task.pilot_id", back_populates="pilot")
    tasks_as_drone = relationship("Task", foreign_keys="Task.drone_id", back_populates="drone")
    flight_positions = relationship("FlightPosition", back_populates="device")
    flight_events = relationship("FlightEvent", back_populates="device")
    maintenance_records = relationship("MaintenanceRecord", back_populates="device")


class FlightPosition(Base):
    __tablename__ = "flight_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float, nullable=False)
    speed = Column(Float, default=0.0)
    heading = Column(Float, default=0.0)
    battery_percent = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    device = relationship("Device", back_populates="flight_positions")


class FlightEvent(Base):
    __tablename__ = "flight_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    event_type = Column(String(30), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    details_json = Column(Text, default="{}")
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    task = relationship("Task", back_populates="flight_events")
    device = relationship("Device", back_populates="flight_events")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    alert_type = Column(String(30), nullable=False)
    severity = Column(String(20), nullable=False, default="warning")
    message = Column(Text, default="")
    is_read = Column(Integer, default=0)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    details_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    task = relationship("Task", back_populates="alerts")


class MediaFile(Base):
    __tablename__ = "media_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    file_type = Column(String(20), nullable=False)
    file_url = Column(String(500), nullable=False)
    file_size = Column(Integer, default=0)
    thumbnail_url = Column(String(500), default="")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    taken_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    task = relationship("Task", back_populates="media_files")


class AnomalyPoint(Base):
    __tablename__ = "anomaly_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    anomaly_type = Column(String(50), default="")
    description = Column(Text, default="")
    severity = Column(String(20), default="warning")
    media_file_ids_json = Column(Text, default="[]")
    is_resolved = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    task = relationship("Task", back_populates="anomalies")


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    maintenance_type = Column(String(30), nullable=False)
    description = Column(Text, default="")
    performed_by = Column(String(100), default="")
    performed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    next_maintenance_date = Column(DateTime, nullable=True)
    cost = Column(Float, default=0.0)

    device = relationship("Device", back_populates="maintenance_records")
