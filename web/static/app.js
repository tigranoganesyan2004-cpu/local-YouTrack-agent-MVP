
let currentMode = "auto";

const statusBox = document.getElementById("system-status");
const actionResult = document.getElementById("action-result");
const responseBox = document.getElementById("response-box");
const historyBox = document.getElementById("history-box");
const queryInput = document.getElementById("query-input");

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

function renderResponse(result) {
  let lines = [];

  if (result.used_llm === true) {
    lines.push("[через LLM]");
  } else if (result.used_llm === false) {
    lines.push("[без LLM]");
  }

  lines.push(result.short_answer || "");

  if (result.evidence && result.evidence.length) {
    lines.push("\nОснование:");
    result.evidence.forEach(x => lines.push(" - " + x));
  }

  if (result.limitations && result.limitations.length) {
    lines.push("\nОграничения:");
    result.limitations.forEach(x => lines.push(" - " + x));
  }

  if (result.used_issue_ids && result.used_issue_ids.length) {
    lines.push("\nИспользованные задачи:");
    result.used_issue_ids.forEach(x => lines.push(" - " + x));
  }

  if (result.tasks && result.tasks.length) {
    lines.push("\nНайденные задачи:");
    result.tasks.slice(0, 10).forEach(t => {
      lines.push(` - ${t.issue_id} | ${t.status} | ${t.priority} | ${t.summary}`);
    });
  }

  responseBox.textContent = lines.join("\n");
}

async function sendQuery() {
  const query = queryInput.value.trim();
  if (!query) {
    responseBox.textContent = "Введи запрос.";
    return;
  }

  responseBox.textContent = "Обработка запроса...";

  const res = await fetch("/api/query", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      query: query,
      mode: currentMode
    })
  });

  const data = await res.json();

  if (!data.ok) {
    responseBox.textContent = data.message;
    return;
  }

  renderResponse(data.data);
  await loadHistory();
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
    lines.push(`Длительность (мс): ${row[5] || 0}`);
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
document.getElementById("send-btn").addEventListener("click", sendQuery);

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