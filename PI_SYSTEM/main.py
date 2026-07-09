# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

import logging
from logging.handlers import TimedRotatingFileHandler
from contextlib import asynccontextmanager

import os
import sys
import io
import json
import time
import signal
import atexit
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from collections import defaultdict


# =============================================================================
# stdout / stderr UTF-8
# =============================================================================
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
except Exception:
    pass


# =============================================================================
# Base path
# =============================================================================
base_dir = os.path.dirname(os.path.abspath(__file__))


# =============================================================================
# Logging
# =============================================================================
def setup_logger() -> logging.Logger:
    log_dir = os.path.join(base_dir, "api_log")
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, "api.log")

    log_format = logging.Formatter(
        "%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()

    file_handler = TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        interval=1,
        backupCount=90,
        encoding="utf-8",
        utc=False,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format)
    file_handler.suffix = "%Y-%m-%d"

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(log_format)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # 關閉 uvicorn access log，避免顯示完整 query string
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.access").propagate = False

    for logger_name in [
        "uvicorn",
        "uvicorn.error",
        "fastapi",
    ]:
        uv_logger = logging.getLogger(logger_name)
        uv_logger.setLevel(logging.INFO)
        uv_logger.propagate = True

    return logging.getLogger("main")


logger = setup_logger()


def flush_all_logs() -> None:
    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except Exception:
            pass


# =============================================================================
# Runtime state
# =============================================================================
RUNTIME_DIR = os.path.join(base_dir, "api_log", "runtime")
os.makedirs(RUNTIME_DIR, exist_ok=True)

STATE_FILE = os.path.join(RUNTIME_DIR, "api_runtime_state.json")

PROCESS_START_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
PROCESS_PID = os.getpid()

_shutdown_reason: Optional[str] = None
_heartbeat_stop = threading.Event()
_runtime_state_lock = threading.Lock()


def write_runtime_state(
    status: str,
    reason: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    data: Dict[str, Any] = {
        "status": status,
        "reason": reason,
        "pid": PROCESS_PID,
        "process_start_time": PROCESS_START_TIME,
        "last_update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": time.time(),
    }

    if extra:
        data.update(extra)

    tmp_path = os.path.join(
        RUNTIME_DIR,
        f"api_runtime_state.{PROCESS_PID}.{threading.get_ident()}.tmp"
    )

    with _runtime_state_lock:
        for attempt in range(1, 6):
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                os.replace(tmp_path, STATE_FILE)
                return

            except PermissionError:
                if attempt >= 5:
                    logger.exception("Failed to write runtime state after retries.")
                    return
                time.sleep(0.2)

            except Exception:
                logger.exception("Failed to write runtime state")
                return

            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass


def read_runtime_state() -> Optional[Dict[str, Any]]:
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to read runtime state")
        return None


def check_previous_runtime_state() -> None:
    previous = read_runtime_state()

    if not previous:
        logger.info("No previous runtime state found")
        return

    status = previous.get("status")
    reason = previous.get("reason")
    pid = previous.get("pid")
    start_time = previous.get("process_start_time")
    last_update = previous.get("last_update_time")

    if status == "running":
        logger.warning(
            "Previous API process did not shutdown cleanly. "
            "previous_pid=%s, previous_start_time=%s, last_heartbeat=%s",
            pid,
            start_time,
            last_update,
        )
    else:
        logger.info(
            "Previous API process ended. status=%s, reason=%s, previous_pid=%s, "
            "previous_start_time=%s, last_update=%s",
            status,
            reason,
            pid,
            start_time,
            last_update,
        )


def heartbeat_loop() -> None:
    while not _heartbeat_stop.is_set():
        write_runtime_state(
            status="running",
            reason="heartbeat",
            extra={
                "heartbeat_interval_sec": 10,
                "worker_pid": os.getpid(),
            },
        )
        _heartbeat_stop.wait(10)


# =============================================================================
# Shutdown logging
# =============================================================================
def mark_shutdown(reason: str, level: int = logging.INFO) -> None:
    global _shutdown_reason

    if _shutdown_reason:
        return

    _shutdown_reason = reason

    logger.log(
        level,
        "API process is stopping. reason=%s, pid=%s",
        reason,
        PROCESS_PID,
    )

    write_runtime_state(
        status="stopped",
        reason=reason,
        extra={
            "process_end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )

    flush_all_logs()


def on_process_exit() -> None:
    reason = _shutdown_reason or "python_process_exit_atexit_unknown_reason"
    mark_shutdown(reason)


atexit.register(on_process_exit)


def handle_sigint(signum, frame) -> None:
    mark_shutdown("SIGINT received. Usually Ctrl+C.", logging.WARNING)
    raise KeyboardInterrupt


def handle_sigterm(signum, frame) -> None:
    mark_shutdown("SIGTERM received. Process termination requested.", logging.WARNING)
    sys.exit(0)


try:
    signal.signal(signal.SIGINT, handle_sigint)
except Exception:
    logger.exception("Failed to register SIGINT handler")

try:
    signal.signal(signal.SIGTERM, handle_sigterm)
except Exception:
    logger.exception("Failed to register SIGTERM handler")


# =============================================================================
# Windows console close / shutdown handler
# =============================================================================
def install_windows_console_handler() -> None:
    if os.name != "nt":
        return

    try:
        import ctypes

        CTRL_C_EVENT = 0
        CTRL_BREAK_EVENT = 1
        CTRL_CLOSE_EVENT = 2
        CTRL_LOGOFF_EVENT = 5
        CTRL_SHUTDOWN_EVENT = 6

        event_names = {
            CTRL_C_EVENT: "CTRL_C_EVENT. Usually Ctrl+C.",
            CTRL_BREAK_EVENT: "CTRL_BREAK_EVENT. Usually Ctrl+Break.",
            CTRL_CLOSE_EVENT: "CTRL_CLOSE_EVENT. CMD window close button X was pressed.",
            CTRL_LOGOFF_EVENT: "CTRL_LOGOFF_EVENT. Windows user logoff.",
            CTRL_SHUTDOWN_EVENT: "CTRL_SHUTDOWN_EVENT. Windows shutdown or restart.",
        }

        HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

        def console_ctrl_handler(ctrl_type):
            reason = event_names.get(
                ctrl_type,
                f"UNKNOWN_WINDOWS_CONSOLE_EVENT={ctrl_type}",
            )
            mark_shutdown(reason, logging.WARNING)
            return True

        install_windows_console_handler._handler_ref = HandlerRoutine(console_ctrl_handler)

        ok = ctypes.windll.kernel32.SetConsoleCtrlHandler(
            install_windows_console_handler._handler_ref,
            True,
        )

        if ok:
            logger.info("Windows console control handler installed")
        else:
            logger.warning("Failed to install Windows console control handler")

    except Exception:
        logger.exception("Failed to install Windows console handler")


install_windows_console_handler()


# =============================================================================
# Uncaught exception logging
# =============================================================================
def handle_uncaught_exception(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        mark_shutdown("KeyboardInterrupt uncaught. Usually Ctrl+C.", logging.WARNING)
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.critical(
        "Uncaught exception caused process crash",
        exc_info=(exc_type, exc_value, exc_traceback),
    )

    write_runtime_state(
        status="crashed",
        reason="uncaught_exception_process_crash",
        extra={
            "process_end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "exception_type": str(exc_type),
            "exception_value": str(exc_value),
        },
    )

    mark_shutdown("uncaught_exception_process_crash", logging.CRITICAL)
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = handle_uncaught_exception


# =============================================================================
# Load routers
# =============================================================================
from routers.piaoi.density import date_reset, trend, get_defects, recipe_same_point
from routers.piaoi.common import (
    editor,
    spec_editor,
    editor_summary,
    density_csv,
    density_avg,
)
from routers.piaoi.aoi_inspection_density import (
    aoi_inspection_density,
    aoi_inspection_density_defect_map,
    aoi_inspection_density_trend,
)
from routers.piaoi.ol_defect_map_phase1 import ol_defect_map
from routers.piaoi.capa import aoi_capa, aoi_capa_save
from routers.piaoi.bpi_density import bpi_density, get_cst_defects
from routers.piaoi.bpi_api_same_point_pair import bpi_same_point
from routers.cell_aoi_to_array import cell_aoi_to_array


# =============================================================================
# FastAPI app
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI lifespan startup triggered. pid=%s", os.getpid())

    check_previous_runtime_state()

    write_runtime_state(
        status="running",
        reason="fastapi_lifespan_startup",
        extra={
            "app_title": "L6AN0 PI SYSTEM",
            "base_dir": base_dir,
            "worker_pid": os.getpid(),
        },
    )

    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        name=f"api-heartbeat-thread-{os.getpid()}",
        daemon=True,
    )
    heartbeat_thread.start()

    try:
        yield
    finally:
        logger.info("FastAPI lifespan shutdown triggered. pid=%s", os.getpid())
        _heartbeat_stop.set()
        mark_shutdown("fastapi_lifespan_shutdown")


app = FastAPI(
    title="L6AN0 PI SYSTEM",
    lifespan=lifespan,
)


# =============================================================================
# Runtime usage monitor
# =============================================================================
ACTIVE_USERS: Dict[str, Dict[str, Any]] = {}
ROUTE_COUNTER = defaultdict(int)
USAGE_LOCK = threading.Lock()

ACTIVE_WINDOW_SEC = 300


@app.middleware("http")
async def usage_monitor_middleware(request: Request, call_next):
    start_ts = time.time()

    client_ip = request.client.host if request.client else "unknown"
    method = request.method
    path = request.url.path

    status_code: Any = "ERR"

    try:
        response: Response = await call_next(request)
        status_code = response.status_code
        return response

    finally:
        cost_ms = round((time.time() - start_ts) * 1000, 1)
        now_ts = time.time()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with USAGE_LOCK:
            ACTIVE_USERS[client_ip] = {
                "ip": client_ip,
                "last_seen": now_str,
                "last_seen_ts": now_ts,
                "last_path": path,
                "last_method": method,
                "pid": os.getpid(),
            }

            ROUTE_COUNTER[path] += 1

            active_count = sum(
                1 for u in ACTIVE_USERS.values()
                if now_ts - float(u.get("last_seen_ts", 0)) <= ACTIVE_WINDOW_SEC
            )

        logger.info(
            "[ACCESS] ip=%s method=%s path=%s status=%s cost_ms=%s active_users_5min=%s pid=%s",
            client_ip,
            method,
            path,
            status_code,
            cost_ms,
            active_count,
            os.getpid(),
        )


@app.get("/runtime/usage")
async def runtime_usage():
    now_ts = time.time()

    with USAGE_LOCK:
        active_users = [
            {
                "ip": u["ip"],
                "last_seen": u["last_seen"],
                "last_path": u["last_path"],
                "last_method": u["last_method"],
                "pid": u.get("pid"),
            }
            for u in ACTIVE_USERS.values()
            if now_ts - float(u.get("last_seen_ts", 0)) <= ACTIVE_WINDOW_SEC
        ]

        return {
            "ok": True,
            "pid": os.getpid(),
            "process_start_time": PROCESS_START_TIME,
            "active_window_sec": ACTIVE_WINDOW_SEC,
            "active_user_count": len(active_users),
            "active_users": active_users,
            "route_counter": dict(ROUTE_COUNTER),
        }


@app.get("/runtime/state")
async def runtime_state():
    return {
        "ok": True,
        "current_pid": os.getpid(),
        "process_start_time": PROCESS_START_TIME,
        "runtime_state_file": read_runtime_state(),
    }


# =============================================================================
# Static files
# =============================================================================
static_path = os.path.join(base_dir, "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")
logger.info("static_path=%s", static_path)


# =============================================================================
# CORS
# =============================================================================
origins = [
    "http://localhost:8204",
    "http://127.0.0.1:8204",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=(
        r"^http://("
        r"10\.\d+\.\d+\.\d+|"
        r"192\.168\.\d+\.\d+|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+"
        r"):8204$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Routers
# =============================================================================
app.include_router(density_csv.router, prefix="/common")
app.include_router(density_avg.router, prefix="/common")
app.include_router(editor.router, prefix="/common")
app.include_router(spec_editor.router, prefix="/common")
app.include_router(editor_summary.router, prefix="/common")

app.include_router(ol_defect_map.router, prefix="/aoi_ol_defect_map")

app.include_router(date_reset.router, prefix="/aoi_density")
app.include_router(get_defects.router, prefix="/aoi_density")
app.include_router(recipe_same_point.router, prefix="/aoi_density")
app.include_router(trend.router, prefix="/aoi_density")

app.include_router(aoi_inspection_density.router, prefix="/aoi_inspection_density")
app.include_router(aoi_inspection_density_defect_map.router, prefix="/aoi_inspection_density")
app.include_router(aoi_inspection_density_trend.router, prefix="/aoi_inspection_density")

app.include_router(aoi_capa.router, prefix="/aoi_capa")
app.include_router(aoi_capa_save.router, prefix="/aoi_capa")

app.include_router(bpi_density.router, prefix="/bpi_density")
app.include_router(get_cst_defects.router, prefix="/bpi_density")

app.include_router(bpi_same_point.router, prefix="/bpi_same_point")

app.include_router(cell_aoi_to_array.router, prefix="/cell_aoi_to_array")

logger.info("All routers loaded successfully")


# =============================================================================
# Entry point
# =============================================================================
if __name__ == "__main__":
    import uvicorn

    logger.info("============================================================")
    logger.info("L6AN0 PI SYSTEM API starting")
    logger.info("base_dir=%s", base_dir)
    logger.info("log_dir=%s", os.path.join(base_dir, "api_log"))
    logger.info("pid=%s", PROCESS_PID)
    logger.info("process_start_time=%s", PROCESS_START_TIME)
    logger.info("============================================================")

    check_previous_runtime_state()

    write_runtime_state(
        status="running",
        reason="process_start",
        extra={
            "host": "0.0.0.0",
            "port": 8104,
            "base_dir": base_dir,
        },
    )

    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        name="api-heartbeat-thread",
        daemon=True,
    )
    heartbeat_thread.start()

    try:
        logger.info("Starting uvicorn host=0.0.0.0 port=8104")

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8104,
            log_config=None,
            access_log=False,
        )

        mark_shutdown("uvicorn_run_returned_normally")

    except KeyboardInterrupt:
        mark_shutdown("KeyboardInterrupt caught in main. Usually Ctrl+C.", logging.WARNING)

    except SystemExit:
        mark_shutdown("SystemExit caught in main.", logging.WARNING)
        raise

    except Exception:
        logger.exception("Fatal exception in main")

        write_runtime_state(
            status="crashed",
            reason="fatal_exception_in_main",
            extra={
                "process_end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

        mark_shutdown("fatal_exception_in_main", logging.CRITICAL)
        raise

    finally:
        _heartbeat_stop.set()
        flush_all_logs()