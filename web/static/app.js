let currentMode = "auto";
let activeController = null;
let timerInterval = null;
let startedAt = null;

const statusBox = document.getElementById("system-status");
const actionResult = document.getElementById("action-result");
const responseBox = document.getElementById("response-box");
const historyBox = document.getElementById("history-box");
const queryInput = document.getElementById("query-input");
const sendBtn = document.getElementById("send-btn");
const stopBtn = document.getElementById("stop-btn");
const requestState = document.getElementById("request-state");
const requestTimer = document.getElementById("request-timer");

function formatMs(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function startTimer() {
  startedAt = performance.now();
  requestTimer.textContent = "00:00";

  timerInterval = setInterval(() => {
    const elapsed = performance.now() - startedAt;
    requestTimer.textContent = formatMs(elapsed);
  }, 500);
}

function stopTimer(finalMs = null) {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }

  if (finalMs !== null) {
    requestTimer.textContent = formatMs(finalMs);
  }
}

function setRunningState(isRunning) {
  sendBtn.disabled = isRunning;
  stopBtn.disabled = !isRunning;
  queryInput.disabled = isRunning;
  requestState.textContent = isRunning ? "Запрос выполняется..." : "Готов к работе";
}

async function loadStatus() {
  const res = await fetch("/api/status");
  const data = await res.json();

  if (!data.ok) {
    statusBox.textContent = "Не удалось получить статус системы";
    return;
  }

  const s = data.data;
  statusBox.textContent =
    `Данные: ${s.prepared_data ? "OK" : "НЕТ"} | ` +
    `Индекс: ${s.index_ready ? "OK" : "НЕТ"} | ` +
    `Ollama: ${s.ollama_ready ? "OK" : "НЕТ"} | ` +
    `Режим: ${currentMode}`;
}

async function prepareData() {
  actionResult.textContent = "Подготовка данных...";
  const res = await fetch("/api/prepare", { method: "POST" });
  const data = await res.json();

  if (!data.ok) {
    actionResult.textContent = data.message;
    return;
  }

  const report = data.data.report_lines || [];
  actionResult.textContent =
    data.message + "\n\n" + report.map(x => "• " + x).join("\n");

  await loadStatus();
}

async function rebuildIndex() {
  actionResult.textContent = "Пересборка индекса...";
  const res = await fetch("/api/rebuild-index", { method: "POST" });
  const data = await res.json();

  if (!data.ok) {
    actionResult.textContent = data.message;
    return;
  }

  const r = data.data;
  actionResult.textContent =
    `${data.message}\n\n` +
    `Всего задач: ${r.tasks_total}\n` +
    `Успешно проиндексировано: ${r.indexed_total}\n` +
    `Пропущено пустых semantic_text: ${r.skipped_empty_semantic_text}\n` +
    `Пропущено плохих векторов: ${r.skipped_bad_vector}\n` +
    `Ошибок эмбеддинга: ${r.embedding_errors}\n` +
    `Размерность embedding: ${r.embedding_dim}`;

  await loadStatus();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderList(title, items) {
  if (!items || !items.length) return "";
  return `
    <div class="response-section">
      <div class="response-title">${escapeHtml(title)}</div>
      <ul>
        ${items.map(x => `<li>${escapeHtml(x)}</li>`).join("")}
      </ul>
    </div>
  `;
}

function renderTasks(tasks) {
  if (!tasks || !tasks.length) return "";

  const rows = tasks.slice(0, 10).map(t => `
    <tr>
      <td>${escapeHtml(t.issue_id || "")}</td>
      <td>${escapeHtml(t.status || "")}</td>
      <td>${escapeHtml(t.priority || "")}</td>
      <td>${escapeHtml(t.summary || "")}</td>
    </tr>
  `).join("");

  return `
    <div class="response-section">
      <div class="response-title">Найденные задачи</div>
      <table class="tasks-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Статус</th>
            <th>Приоритет</th>
            <th>Заголовок</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderResponse(result) {
  const modeLabel = result.used_llm === true
    ? "[через LLM]"
    : result.used_llm === false
      ? "[без LLM]"
      : "";

  const duration = result.duration_ms !== undefined
    ? `<div class="response-meta">Длительность: ${formatMs(result.duration_ms)}</div>`
    : "";

  responseBox.innerHTML = `
    <div class="response-header">
      <div class="response-mode">${escapeHtml(modeLabel)}</div>
      ${duration}
    </div>

    <div class="response-short-answer">
      ${escapeHtml(result.short_answer || "")}
    </div>

    ${renderList("Основание", result.evidence || [])}
    ${renderList("Ограничения", result.limitations || [])}
    ${renderList("Использованные задачи", result.used_issue_ids || [])}
    ${renderTasks(result.tasks || [])}
  `;
}

function parseSseBuffer(buffer) {
  const events = [];
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";

  for (const part of parts) {
    if (!part.trim()) continue;

    let eventType = "message";
    let dataStr = "";

    for (const line of part.split("\n")) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        dataStr = line.slice(6);
      }
    }

    if (dataStr) {
      events.push({ type: eventType, raw: dataStr });
    }
  }

  return { events, remainder };
}

async function sendQuery() {
  const query = queryInput.value.trim();
  if (!query) {
    responseBox.innerHTML = `<div class="empty-state">Введи запрос.</div>`;
    return;
  }

  activeController = new AbortController();
  setRunningState(true);
  responseBox.innerHTML = `<div class="empty-state">Обработка запроса...</div>`;
  startTimer();

  let buffer = "";
  let streamText = "";
  let resultRendered = false;

  try {
    const response = await fetch("/api/query-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, mode: currentMode }),
      signal: activeController.signal,
    });

    if (!response.ok) {
      responseBox.innerHTML = `<div class="error-state">Ошибка сервера: ${response.status}</div>`;
      requestState.textContent = "Ошибка";
      stopTimer();
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      const { events, remainder } = parseSseBuffer(buffer);
      buffer = remainder;

      for (const event of events) {
        if (event.type === "token") {
          // Токены копим, но не показываем как основной ответ:
          // у нас LLM возвращает JSON, а не человекочитаемый текст.
          try {
            const payload = JSON.parse(event.raw);
            streamText += payload.text ?? "";
            responseBox.innerHTML = `<div class="empty-state">Модель формирует ответ...</div>`;
          } catch {
            responseBox.innerHTML = `<div class="empty-state">Модель формирует ответ...</div>`;
          }

        } else if (event.type === "result") {
          try {
            const result = JSON.parse(event.raw);
            renderResponse(result);
            resultRendered = true;
            requestState.textContent = "Выполнено";
            stopTimer(result.duration_ms ?? null);
          } catch {
            responseBox.innerHTML = `<div class="error-state">Ошибка разбора ответа сервера.</div>`;
            requestState.textContent = "Ошибка";
            stopTimer();
          }

        } else if (event.type === "done") {
          if (!resultRendered) {
            responseBox.innerHTML = `<div class="warning-state">Стрим завершен без итогового результата.</div>`;
            requestState.textContent = "Завершено";
            stopTimer();
          }
        }
      }
    }

    await loadHistory();

  } catch (err) {
    if (err.name === "AbortError") {
      responseBox.innerHTML = `<div class="warning-state">Запрос остановлен пользователем.</div>`;
      requestState.textContent = "Остановлено";
    } else {
      responseBox.innerHTML = `<div class="error-state">Ошибка соединения: ${escapeHtml(err.message || err)}</div>`;
      requestState.textContent = "Ошибка";
    }
    stopTimer();
  } finally {
    activeController = null;
    setRunningState(false);
  }
}

function stopQuery() {
  if (activeController) {
    activeController.abort();
  }
}

async function loadHistory() {
  const res = await fetch("/api/history?limit=10");
  const data = await res.json();

  if (!data.ok) {
    historyBox.textContent = data.message;
    return;
  }

  const rows = data.data || [];
  if (!rows.length) {
    historyBox.textContent = "История пока пуста.";
    return;
  }

  let lines = [];
  rows.forEach(row => {
    lines.push("================================================");
    lines.push(`Время: ${row[0]}`);
    lines.push(`Режим: ${row[1]}`);
    lines.push(`Запрос: ${row[2]}`);
    lines.push(`Найденные ID: ${row[4] || ""}`);
    lines.push(`Длительность: ${formatMs(row[5] || 0)}`);
    lines.push(`LLM: ${row[6] ? "да" : "нет"}`);
    if (row[7]) {
      lines.push(`Ошибка: ${row[7]}`);
    }
  });

  historyBox.textContent = lines.join("\n");
}

document.getElementById("prepare-btn").addEventListener("click", prepareData);
document.getElementById("rebuild-btn").addEventListener("click", rebuildIndex);
document.getElementById("history-btn").addEventListener("click", loadHistory);
sendBtn.addEventListener("click", sendQuery);
stopBtn.addEventListener("click", stopQuery);

queryInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendQuery();
  }
});

document.querySelectorAll(".mode-btn").forEach(btn => {
  btn.addEventListener("click", async () => {
    document.querySelectorAll(".mode-btn").forEach(x => x.classList.remove("active"));
    btn.classList.add("active");
    currentMode = btn.dataset.mode;
    await loadStatus();
  });
});

loadStatus();
loadHistory();