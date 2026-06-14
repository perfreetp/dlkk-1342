from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import task_service
from app.schemas.schemas import TaskCreate, TaskUpdate, TaskOut, TaskMergeRequest

router = APIRouter(prefix="/api/v1/tasks", tags=["任务管理"])


@router.post("/", response_model=TaskOut)
async def create_task(task_in: TaskCreate, db: AsyncSession = Depends(get_db)):
    return await task_service.create_task(db, task_in)


@router.get("/")
async def list_tasks(
    status: str = Query(None),
    task_type: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1),
    db: AsyncSession = Depends(get_db),
):
    items, total = await task_service.list_tasks(db, status=status, task_type=task_type, page=page, page_size=page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, task_in: TaskUpdate, db: AsyncSession = Depends(get_db)):
    task = await task_service.update_task(db, task_id, task_in)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(task_id: int, db: AsyncSession = Depends(get_db)):
    try:
        task = await task_service.cancel_task(db, task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/start", response_model=TaskOut)
async def start_task(task_id: int, db: AsyncSession = Depends(get_db)):
    try:
        task = await task_service.start_task(db, task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/complete", response_model=TaskOut)
async def complete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    try:
        task = await task_service.complete_task(db, task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/merge", response_model=TaskOut)
async def merge_tasks(merge_in: TaskMergeRequest, db: AsyncSession = Depends(get_db)):
    return await task_service.merge_tasks(db, merge_in)


@router.post("/{task_id}/assign", response_model=TaskOut)
async def assign_task(
    task_id: int,
    pilot_id: int = Query(...),
    drone_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        task = await task_service.assign_pilot_and_drone(db, task_id, pilot_id=pilot_id, drone_id=drone_id)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
