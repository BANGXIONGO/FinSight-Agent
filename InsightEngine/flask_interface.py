"""
Flask interface for InsightEngine.
Provides task-based APIs and a lightweight dashboard.
"""

from __future__ import annotations

import html
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, Response, jsonify, render_template, request
from loguru import logger

from .agent import DeepSearchAgent, create_agent
from .utils.config import settings


insight_bp = Blueprint(
    "insight_engine",
    __name__,
    template_folder="templates",
    static_folder="static",
)


OUTPUT_DIR = Path("insight_engine_streamlit_reports")
MAX_LOG_LINES = 1500
MAX_TASKS = 20


tasks_lock = threading.Lock()
tasks: Dict[str, "InsightTask"] = {}
current_task_id: Optional[str] = None
engine_ready = False
engine_error = ""


@dataclass
class InsightTask:
    task_id: str
    query: str
    status: str = "pending"  # pending, running, completed, error
    progress: int = 0
    error_message: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    report_markdown: str = ""
    report_html: str = ""
    report_file_path: str = ""
    report_file_name: str = ""
    paragraphs_total: int = 0
    paragraphs_completed: int = 0
    is_agent_completed: bool = False
    log_lines: List[str] = field(default_factory=list)
    agent: Optional[DeepSearchAgent] = None

    def update_status(self, status: str, progress: Optional[int] = None, error_message: str = "") -> None:
        self.status = status
        if progress is not None:
            self.progress = max(0, min(100, int(progress)))
        if error_message:
            self.error_message = error_message
        self.updated_at = datetime.now()

    def append_log(self, message: str) -> None:
        line = str(message).rstrip("\n")
        if not line:
            return
        self.log_lines.append(line)
        if len(self.log_lines) > MAX_LOG_LINES:
            self.log_lines = self.log_lines[-MAX_LOG_LINES:]
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "query": self.query,
            "status": self.status,
            "progress": self.progress,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "paragraphs_total": self.paragraphs_total,
            "paragraphs_completed": self.paragraphs_completed,
            "report_ready": bool(self.report_markdown),
            "report_file_name": self.report_file_name,
            "report_file_path": self.report_file_path,
            "log_count": len(self.log_lines),
        }


def initialize_insight_engine() -> bool:
    global engine_ready, engine_error
    try:
        _ = create_agent()
        engine_ready = True
        engine_error = ""
        logger.info("InsightEngine Flask interface initialized.")
        return True
    except Exception as exc:
        engine_ready = False
        engine_error = str(exc)
        logger.exception(f"InsightEngine initialization failed: {exc}")
        return False


def _db_connection_summary() -> Dict[str, str]:
    return {
        "dialect": (settings.DB_DIALECT or "mysql"),
        "host": settings.DB_HOST or "",
        "port": str(settings.DB_PORT or ""),
        "database": settings.DB_NAME or "",
        "user": settings.DB_USER or "",
    }


def _render_markdown_like_html(markdown_text: str) -> str:
    """
    Minimal markdown-like renderer to avoid extra dependency.
    """
    lines = markdown_text.splitlines()
    chunks: List[str] = []
    in_list = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            if in_list:
                chunks.append("</ul>")
                in_list = False
            chunks.append("<div class='gap'></div>")
            continue

        escaped = html.escape(stripped)
        if escaped.startswith("### "):
            if in_list:
                chunks.append("</ul>")
                in_list = False
            chunks.append(f"<h3>{escaped[4:]}</h3>")
        elif escaped.startswith("## "):
            if in_list:
                chunks.append("</ul>")
                in_list = False
            chunks.append(f"<h2>{escaped[3:]}</h2>")
        elif escaped.startswith("# "):
            if in_list:
                chunks.append("</ul>")
                in_list = False
            chunks.append(f"<h1>{escaped[2:]}</h1>")
        elif escaped.startswith("- ") or escaped.startswith("* "):
            if not in_list:
                chunks.append("<ul>")
                in_list = True
            chunks.append(f"<li>{escaped[2:]}</li>")
        else:
            if in_list:
                chunks.append("</ul>")
                in_list = False
            chunks.append(f"<p>{escaped}</p>")

    if in_list:
        chunks.append("</ul>")

    return "\n".join(chunks)


def _safe_query_name(query: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", query).strip("_")
    return safe[:40] or "query"


def _save_report_file(task: InsightTask, report_markdown: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"deep_search_report_{_safe_query_name(task.query)}_{timestamp}.md"
    filepath = OUTPUT_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_markdown)

    task.report_file_name = filename
    task.report_file_path = str(filepath.resolve())


def _refresh_live_progress(task: InsightTask) -> None:
    if not task.agent:
        return

    try:
        summary = task.agent.get_progress_summary()
    except Exception:
        return

    total = int(summary.get("total_paragraphs", 0) or 0)
    completed = int(summary.get("completed_paragraphs", 0) or 0)
    is_completed = bool(summary.get("is_completed", False))

    task.paragraphs_total = total
    task.paragraphs_completed = completed
    task.is_agent_completed = is_completed

    if total > 0:
        base_progress = int((completed / total) * 80) + 15
        base_progress = min(base_progress, 95)
        task.progress = max(task.progress, base_progress)
    task.updated_at = datetime.now()


def _cleanup_old_tasks() -> None:
    with tasks_lock:
        if len(tasks) <= MAX_TASKS:
            return
        ordered = sorted(tasks.values(), key=lambda t: t.created_at)
        overflow = len(tasks) - MAX_TASKS
        for task in ordered[:overflow]:
            tasks.pop(task.task_id, None)


def run_insight_task(task: InsightTask) -> None:
    global current_task_id
    sink_id = None

    try:
        task.update_status("running", 8)
        task.append_log(f"{datetime.now().isoformat()} | Task started.")

        task.agent = create_agent()
        task.update_status("running", 15)
        task.append_log(f"{datetime.now().isoformat()} | Agent initialized.")

        sink_id = logger.add(
            task.append_log,
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        )

        report_markdown = task.agent.research(task.query, save_report=False)
        _refresh_live_progress(task)

        task.report_markdown = report_markdown
        task.report_html = _render_markdown_like_html(report_markdown)
        _save_report_file(task, report_markdown)

        task.update_status("completed", 100)
        task.append_log(f"{datetime.now().isoformat()} | Task completed.")

    except Exception as exc:
        logger.exception(f"Insight task failed: {exc}")
        task.update_status("error", 0, str(exc))
        task.append_log(f"{datetime.now().isoformat()} | ERROR: {exc}")
    finally:
        if sink_id is not None:
            logger.remove(sink_id)
        with tasks_lock:
            if current_task_id == task.task_id:
                current_task_id = None
        _cleanup_old_tasks()


@insight_bp.route("/", methods=["GET"])
def dashboard():
    return render_template("insight_dashboard.html")


@insight_bp.route("/api/status", methods=["GET"])
def api_status():
    with tasks_lock:
        current_task = tasks.get(current_task_id) if current_task_id else None
        payload = {
            "success": True,
            "engine_ready": engine_ready,
            "engine_error": engine_error,
            "data_source": _db_connection_summary(),
            "current_task": current_task.to_dict() if current_task else None,
        }
    return jsonify(payload)


@insight_bp.route("/api/generate", methods=["POST"])
def api_generate():
    global current_task_id

    data = request.get_json(silent=True) or {}
    query = str(data.get("query", "")).strip()
    if not query:
        return jsonify({"success": False, "error": "query is required"}), 400

    if not engine_ready:
        ok = initialize_insight_engine()
        if not ok:
            return jsonify({"success": False, "error": f"engine initialization failed: {engine_error}"}), 500

    with tasks_lock:
        if current_task_id and current_task_id in tasks and tasks[current_task_id].status == "running":
            return jsonify(
                {
                    "success": False,
                    "error": "another task is running",
                    "current_task": tasks[current_task_id].to_dict(),
                }
            ), 409

        task_id = f"insight_{int(time.time() * 1000)}"
        task = InsightTask(task_id=task_id, query=query)
        tasks[task_id] = task
        current_task_id = task_id

    thread = threading.Thread(target=run_insight_task, args=(task,), daemon=True)
    thread.start()

    return jsonify({"success": True, "task_id": task_id, "task": task.to_dict()})


@insight_bp.route("/api/progress/<task_id>", methods=["GET"])
def api_progress(task_id: str):
    with tasks_lock:
        task = tasks.get(task_id)

    if not task:
        return jsonify({"success": False, "error": "task not found"}), 404

    if task.status == "running":
        _refresh_live_progress(task)

    return jsonify({"success": True, "task": task.to_dict()})


@insight_bp.route("/api/logs/<task_id>", methods=["GET"])
def api_logs(task_id: str):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return jsonify({"success": False, "error": "task not found"}), 404

    limit = request.args.get("limit", default=300, type=int)
    limit = max(1, min(limit, MAX_LOG_LINES))
    return jsonify({"success": True, "logs": task.log_lines[-limit:]})


@insight_bp.route("/api/result/<task_id>", methods=["GET"])
def api_result(task_id: str):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return jsonify({"success": False, "error": "task not found"}), 404

    if task.status != "completed":
        return jsonify({"success": False, "error": "task not completed", "task": task.to_dict()}), 400

    return jsonify(
        {
            "success": True,
            "task": task.to_dict(),
            "report_markdown": task.report_markdown,
            "report_html": task.report_html,
        }
    )


@insight_bp.route("/api/result/<task_id>/markdown", methods=["GET"])
def api_result_markdown(task_id: str):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return jsonify({"success": False, "error": "task not found"}), 404

    if task.status != "completed":
        return jsonify({"success": False, "error": "task not completed"}), 400

    return Response(task.report_markdown, mimetype="text/markdown")
