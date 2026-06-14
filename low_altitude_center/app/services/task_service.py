from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import async_session
from ..models.models import Task, Device, TaskEvent
from ..schemas.schemas import TaskCreate, TaskUpdate, TaskMergeRequest
from ..core.events import publish_event
from ..core.enums import UNAVAILABLE_DEVICE_STATUSES

VALID_TRANSITIONS = {
    "draft": ["planned", "cancelled"],
    "planned": ["approved", "cancelled"],
    "approved": ["in_progress", "cancelled"],
    "in_progress": ["completed", "cancelled"],
    "completed": [],
    "cancelled": [],
}


async def _transition_status(db: AsyncSession, task: Task, new_status: str, source: str = "manual", description: str = None) -> Task:
    old_status = task.status
    if new_status == old_status:
        return task
    allowed = VALID_TRANSITIONS.get(old_status, [])
    if new_status not in allowed:
        raise ValueError(
            f"Cannot transition task from '{old_status}' to '{new_status}'. "
            f"Allowed transitions: {allowed}"
        )
    task.status = new_status

    event = TaskEvent(
        task_id=task.id,
        event_type="status_changed",
        old_status=old_status,
        new_status=new_status,
        source=source,
        description=description or f"Status changed from {old_status} to {new_status}",
    )
    db.add(event)

    await db.commit()
    await db.refresh(task)
    await db.refresh(event)

    await publish_event(
        event_type="task.status_changed",
        payload={
            "task_id": task.id,
            "old_status": old_status,
            "new_status": new_status,
            "source": source,
            "name": task.name,
            "event_id": event.id,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        },
    )

    return task


async def create_task(db: AsyncSession, task_data: TaskCreate) -> Task:
    task = Task(**task_data.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: int) -> Optional[Task]:
    result = await db.execute(select(Task).where(Task.id == task_id))
    return result.scalars().first()


async def get_task_timeline(db: AsyncSession, task_id: int) -> Optional[list[TaskEvent]]:
    task = await get_task(db, task_id)
    if task is None:
        return None
    result = await db.execute(
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id)
        .order_by(TaskEvent.timestamp.asc())
    )
    return list(result.scalars().all())


async def list_tasks(
    db: AsyncSession,
    status: str = None,
    task_type: str = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    query = select(Task)
    count_query = select(func.count()).select_from(Task)

    if status is not None:
        query = query.where(Task.status == status)
        count_query = count_query.where(Task.status == status)
    if task_type is not None:
        query = query.where(Task.task_type == task_type)
        count_query = count_query.where(Task.task_type == task_type)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    query = query.order_by(Task.id.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def update_task(
    db: AsyncSession, task_id: int, task_data: TaskUpdate
) -> Optional[Task]:
    task = await get_task(db, task_id)
    if task is None:
        return None
    update_data = task_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)
    await db.commit()
    await db.refresh(task)
    return task


async def cancel_task(db: AsyncSession, task_id: int) -> Optional[Task]:
    task = await get_task(db, task_id)
    if task is None:
        return None
    return await _transition_status(db, task, "cancelled")


async def start_task(db: AsyncSession, task_id: int) -> Optional[Task]:
    task = await get_task(db, task_id)
    if task is None:
        return None
    if task.status == "approved":
        return await _transition_status(db, task, "in_progress")
    if task.status in ("draft", "planned"):
        await _transition_status(db, task, "planned")
        await _transition_status(db, task, "approved")
        return await _transition_status(db, task, "in_progress")
    raise ValueError(
        f"Cannot start task with status '{task.status}'. "
        "Task must be in draft, planned, or approved status."
    )


async def complete_task(db: AsyncSession, task_id: int) -> Optional[Task]:
    task = await get_task(db, task_id)
    if task is None:
        return None
    return await _transition_status(db, task, "completed")


async def merge_tasks(db: AsyncSession, merge_req: TaskMergeRequest) -> Task:
    child_tasks = []
    for tid in merge_req.task_ids:
        child = await get_task(db, tid)
        if child is not None:
            child_tasks.append(child)

    combined_summary = " | ".join(
        child.result_summary for child in child_tasks if child.result_summary
    )

    parent = Task(
        name=merge_req.merged_name,
        description=merge_req.merged_description,
        result_summary=combined_summary,
    )
    db.add(parent)
    await db.commit()
    await db.refresh(parent)

    for child in child_tasks:
        child.parent_task_id = parent.id
    await db.commit()

    return parent


async def assign_pilot_and_drone(
    db: AsyncSession, task_id: int, pilot_id: int, drone_id: int
) -> Optional[Task]:
    task = await get_task(db, task_id)
    if task is None:
        return None

    drone_result = await db.execute(select(Device).where(Device.id == drone_id))
    drone = drone_result.scalars().first()
    if drone is None:
        raise ValueError(f"Device with id {drone_id} not found")
    if drone.status in UNAVAILABLE_DEVICE_STATUSES:
        raise ValueError(
            f"Drone '{drone.name}' (id={drone_id}) is currently '{drone.status}' "
            "and cannot be assigned to a task"
        )

    pilot_result = await db.execute(select(Device).where(Device.id == pilot_id))
    pilot = pilot_result.scalars().first()
    if pilot is None:
        raise ValueError(f"Device with id {pilot_id} not found")
    if pilot.status in UNAVAILABLE_DEVICE_STATUSES:
        raise ValueError(
            f"Pilot '{pilot.name}' (id={pilot_id}) is currently '{pilot.status}' "
            "and cannot be assigned to a task"
        )

    task.pilot_id = pilot_id
    task.drone_id = drone_id
    await db.commit()
    await db.refresh(task)
    return task
