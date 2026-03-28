const state = {
  taskId: null,
  pollTimer: null,
  lastLogCount: 0,
  activeTab: "rendered",
};

const dom = {
  queryInput: document.getElementById("queryInput"),
  startBtn: document.getElementById("startBtn"),
  hintText: document.getElementById("hintText"),
  sourceLabel: document.getElementById("sourceLabel"),
  engineStatus: document.getElementById("engineStatus"),
  taskStatus: document.getElementById("taskStatus"),
  progressText: document.getElementById("progressText"),
  paragraphText: document.getElementById("paragraphText"),
  progressPct: document.getElementById("progressPct"),
  progressBar: document.getElementById("progressBar"),
  messageBar: document.getElementById("messageBar"),
  stageList: document.getElementById("stageList"),
  logBox: document.getElementById("logBox"),
  reportRendered: document.getElementById("reportRendered"),
  reportMarkdown: document.getElementById("reportMarkdown"),
  tabButtons: Array.from(document.querySelectorAll(".tab-btn")),
};

function buildSourceText(dataSource) {
  if (!dataSource) return "MySQL";
  const host = dataSource.host || "localhost";
  const port = dataSource.port || "3306";
  const db = dataSource.database || "";
  return `MySQL ${host}:${port}/${db}`;
}

function setHint(text, type = "info") {
  dom.hintText.textContent = text;
  if (type === "error") {
    dom.hintText.style.color = "#dc2626";
    return;
  }
  if (type === "ok") {
    dom.hintText.style.color = "#16a34a";
    return;
  }
  dom.hintText.style.color = "";
}

function setStartDisabled(disabled) {
  dom.startBtn.disabled = disabled;
}

function updateStage(status) {
  const [pending, running, completed] = dom.stageList.querySelectorAll("li");
  pending.className = "";
  running.className = "";
  completed.className = "";

  if (status === "pending") {
    pending.className = "active";
    return;
  }
  if (status === "running") {
    pending.className = "done";
    running.className = "active";
    return;
  }
  if (status === "completed") {
    pending.className = "done";
    running.className = "done";
    completed.className = "done";
    return;
  }
  if (status === "error") {
    pending.className = "done";
    running.className = "failed";
    completed.className = "failed";
  }
}

function normalizeStatus(status) {
  if (status === "pending") return "排队中";
  if (status === "running") return "分析中";
  if (status === "completed") return "已完成";
  if (status === "error") return "失败";
  return "空闲";
}

function updateTask(task) {
  if (!task) {
    dom.taskStatus.textContent = "空闲";
    dom.progressText.textContent = "0%";
    dom.paragraphText.textContent = "0 / 0";
    dom.progressPct.textContent = "0%";
    dom.progressBar.style.width = "0%";
    dom.messageBar.textContent = "等待任务启动";
    updateStage("pending");
    return;
  }

  dom.taskStatus.textContent = normalizeStatus(task.status);
  dom.progressText.textContent = `${task.progress}%`;
  dom.paragraphText.textContent = `${task.paragraphs_completed} / ${task.paragraphs_total}`;
  dom.progressPct.textContent = `${task.progress}%`;
  dom.progressBar.style.width = `${task.progress}%`;

  if (task.status === "error") {
    dom.messageBar.textContent = task.error_message || "任务执行失败";
  } else if (task.status === "completed") {
    dom.messageBar.textContent = `报告已生成：${task.report_file_name || "未命名"}`;
  } else {
    dom.messageBar.textContent = `正在处理查询：${task.query}`;
  }

  updateStage(task.status);
}

function updateLogs(logs) {
  dom.logBox.textContent = logs.join("\n");
  dom.logBox.scrollTop = dom.logBox.scrollHeight;
}

function renderReport(reportHtml, reportMarkdown) {
  dom.reportRendered.innerHTML = reportHtml || "<p>暂无内容</p>";
  dom.reportMarkdown.textContent = reportMarkdown || "";
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok || !payload.success) {
    const message = payload.error || `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

async function loadResult(taskId) {
  const result = await fetchJson(`./api/result/${taskId}`);
  renderReport(result.report_html, result.report_markdown);
}

async function refreshLogs(taskId) {
  const data = await fetchJson(`./api/logs/${taskId}?limit=400`);
  if (data.logs.length !== state.lastLogCount) {
    state.lastLogCount = data.logs.length;
    updateLogs(data.logs);
  }
}

async function refreshTask(taskId) {
  const data = await fetchJson(`./api/progress/${taskId}`);
  const task = data.task;
  updateTask(task);

  if (task.status === "completed") {
    await loadResult(taskId);
    setHint("分析完成。", "ok");
    setStartDisabled(false);
    stopPolling();
    return;
  }

  if (task.status === "error") {
    setHint(`任务失败：${task.error_message || "未知错误"}`, "error");
    setStartDisabled(false);
    stopPolling();
  }
}

function startPolling(taskId) {
  stopPolling();
  state.pollTimer = setInterval(async () => {
    try {
      await Promise.all([refreshTask(taskId), refreshLogs(taskId)]);
    } catch (error) {
      setHint(`轮询失败：${error.message}`, "error");
      stopPolling();
      setStartDisabled(false);
    }
  }, 1500);
}

async function submitTask() {
  const query = dom.queryInput.value.trim();
  if (!query) {
    setHint("请输入分析问题。", "error");
    return;
  }

  setStartDisabled(true);
  setHint("任务已提交，正在启动执行...");
  dom.logBox.textContent = "";
  renderReport("", "");
  state.lastLogCount = 0;

  try {
    const data = await fetchJson("./api/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    });

    state.taskId = data.task_id;
    updateTask(data.task);
    startPolling(state.taskId);
  } catch (error) {
    setHint(`启动失败：${error.message}`, "error");
    setStartDisabled(false);
  }
}

function switchTab(tabName) {
  state.activeTab = tabName;
  dom.tabButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });

  if (tabName === "markdown") {
    dom.reportRendered.classList.add("hidden");
    dom.reportMarkdown.classList.remove("hidden");
    return;
  }
  dom.reportMarkdown.classList.add("hidden");
  dom.reportRendered.classList.remove("hidden");
}

async function bootstrap() {
  dom.startBtn.addEventListener("click", submitTask);

  dom.tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  try {
    const status = await fetchJson("./api/status");
    dom.engineStatus.textContent = status.engine_ready ? "可用" : "异常";
    dom.sourceLabel.textContent = buildSourceText(status.data_source);
    if (!status.engine_ready && status.engine_error) {
      setHint(`引擎初始化失败：${status.engine_error}`, "error");
    } else {
      setHint("准备就绪。");
    }

    if (status.current_task) {
      state.taskId = status.current_task.task_id;
      updateTask(status.current_task);
      if (status.current_task.status === "running") {
        setStartDisabled(true);
        startPolling(state.taskId);
      } else if (status.current_task.status === "completed") {
        await Promise.all([loadResult(state.taskId), refreshLogs(state.taskId)]);
      }
    } else {
      updateTask(null);
    }
  } catch (error) {
    dom.engineStatus.textContent = "异常";
    setHint(`状态加载失败：${error.message}`, "error");
  }
}

bootstrap();
