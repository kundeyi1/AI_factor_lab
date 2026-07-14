import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.ai.generator import factor_generator
from server.backtest.backtester import Backtester
from server.config import STATIC_DIR
from server.data.fetcher import get_available_pools
from server.factors.library import FactorLibrary

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Factor Lab")

executor = ThreadPoolExecutor(max_workers=1)
backtester = Backtester()
jobs: dict[str, dict] = {}
jobs_lock = Lock()
max_pending_jobs = max(1, int(os.getenv("AI_FACTOR_LAB_MAX_PENDING_JOBS", "3")))
max_stored_jobs = max(max_pending_jobs, int(os.getenv("AI_FACTOR_LAB_MAX_STORED_JOBS", "20")))


class ChatRequest(BaseModel):
    message: str
    history: Optional[list[dict[str, str]]] = []
    provider: Optional[str] = "deepseek"
    api_key: Optional[str] = None


class BacktestRequest(BaseModel):
    expression: str
    start_date: str
    end_date: str
    pool: str = "hs300"
    freq: str = "D"
    layers: int = 5


class FactorSaveRequest(BaseModel):
    name: str
    expression: str
    description: str = ""


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}


@app.post("/api/chat")
def chat_with_ai(request: ChatRequest):
    try:
        data = factor_generator.generate_factor(
            request.message,
            history=request.history or [],
            api_key=request.api_key,
            provider=request.provider or "deepseek",
        )
        return {"status": "success", "data": data}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/backtest/run")
def run_backtest(request: BacktestRequest):
    if not request.expression.strip():
        raise HTTPException(status_code=400, detail="因子表达式不能为空。")
    if request.layers not in {3, 5, 10}:
        raise HTTPException(status_code=400, detail="分层数量仅支持 3、5、10。")

    with jobs_lock:
        pending_jobs = sum(job["status"] == "running" for job in jobs.values())
        if pending_jobs >= max_pending_jobs:
            raise HTTPException(status_code=429, detail="当前回测队列已满，请稍后重试。")
        _prune_jobs_locked()
        job_id = uuid.uuid4().hex
        jobs[job_id] = {
            "status": "running",
            "percent": 0,
            "message": "任务已创建",
            "result": None,
            "detail": None,
        }

    def progress(percent: int, message: str):
        jobs[job_id].update({"percent": percent, "message": message})

    def task():
        try:
            result = backtester.run(
                request.expression,
                request.start_date,
                request.end_date,
                request.pool,
                request.freq,
                request.layers,
                progress=progress,
            )
            jobs[job_id].update({"status": "success", "percent": 100, "message": "回测完成", "result": result})
        except Exception as exc:
            logger.exception("backtest failed")
            jobs[job_id].update({"status": "error", "percent": 100, "message": "回测失败", "detail": str(exc)})

    executor.submit(task)
    return {"status": "started", "job_id": job_id}


@app.get("/api/backtest/progress/{job_id}")
def get_progress(job_id: str):
    job = _get_job(job_id)
    return {
        "status": job["status"],
        "percent": job["percent"],
        "message": job["message"],
        "is_running": job["status"] == "running",
    }


@app.get("/api/backtest/result/{job_id}")
def get_result(job_id: str):
    job = _get_job(job_id)
    if job["status"] == "success":
        return {"status": "success", "data": job["result"]}
    if job["status"] == "error":
        return {"status": "error", "detail": job["detail"]}
    return {"status": "running"}


@app.get("/api/factors")
def get_factors():
    return {"status": "success", "data": FactorLibrary.get_all_factors()}


@app.get("/api/pools")
def get_pools():
    return {"status": "success", "data": get_available_pools()}


@app.post("/api/factors")
def save_factor(request: FactorSaveRequest):
    if not request.name.strip() or not request.expression.strip():
        raise HTTPException(status_code=400, detail="因子名称和表达式不能为空。")
    FactorLibrary.save_factor(request.name.strip(), request.expression.strip(), request.description.strip())
    return {"status": "success"}


@app.delete("/api/factors/{name}")
def delete_factor(name: str):
    deleted = FactorLibrary.delete_factor(name.strip())
    return {"status": "success", "deleted": deleted}


def _get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="未找到回测任务。")
    return job


def _prune_jobs_locked() -> None:
    overflow = len(jobs) - max_stored_jobs + 1
    if overflow <= 0:
        return
    completed = [job_id for job_id, job in jobs.items() if job["status"] != "running"]
    for job_id in completed[:overflow]:
        jobs.pop(job_id, None)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
