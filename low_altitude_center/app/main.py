from fastapi import FastAPI
from contextlib import asynccontextmanager

from .core.database import init_db
from .routers import task_router, route_router, airspace_router, device_router, flight_router, alert_router, report_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="低空能力中心后端服务",
    description="提供任务、航线、空域、设备、飞行、告警、报表七类能力，供无人机管理平台、巡检系统和指挥大屏调用",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(task_router.router)
app.include_router(route_router.router)
app.include_router(airspace_router.router)
app.include_router(device_router.router)
app.include_router(flight_router.router)
app.include_router(alert_router.router)
app.include_router(report_router.router)


@app.get("/health", tags=["系统"])
async def health_check():
    return {"status": "ok", "service": "低空能力中心"}
