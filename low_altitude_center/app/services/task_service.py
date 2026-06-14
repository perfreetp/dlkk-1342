from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import async_session
from ..models.models import Task
from ..schemas.schemas import TaskCreate, TaskUpdate, TaskMergeRequest
from ..core.events import publish_event


async def create_task(db: AsyncSession, task_data: TaskCreate) -> Task:
    task = Task(**task_data.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: int) -> Optional[Task]:
    result = await db.execute(select(Task).where(Task.id == task_id))
    return result.scalars().first()


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
    if task.status not in ("draft", "planned", "approved"):
        raise ValueError(
            f"Cannot cancel task with status '{task.status}'. "
            "Only tasks with status draft, planned, or approved can be cancelled."
        )
    task.status = "cancelled"
    await db.commit()
    await db.refresh(task)

    await publish_event(
        event_type="task.status_changed",
        payload={
            "task_id": task.id,
            "old_status": "cancelled",
            "new_status": "cancelled",
            "name": task.name,
        },
    )

    return task


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
    task.pilot_id = pilot_id
    task.drone_id = drone_id
    await db.commit()
    await db.refresh(task)
    return task
