const state = {
  bootstrap: null,
  lastResult: null,
  abortController: null,
  streamBuffer: "",
  suggestionTimer: null,
  selectedExampleCategoryId: null,
  selectedMode: "ai_answer",
  activeChatId: "",
  sidebarCollapsed: false,
};

const els = {};

const FILTER_LABELS_RU = {
  issue_id: "ID задачи",
  status: "статус",
  status_group: "группа статуса",
  workflow_group: "группа процесса",
  functional_customer: "заказчик",
  responsible_dit: "ответственный",
  current_approval_stage: "текущая стадия согласования",
  doc_type: "тип документа",
  pending_approvals: "ожидаемые согласования",
  priority: "приоритет",
};

function normalizeFilterLabel(value) {
  let text = String(value ?? "");
  for (const [raw, label] of Object.entries(FILTER_LABELS_RU)) {
    text = text.replaceAll(raw, label);
  }
  return text;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function badgeClassByBoolean(ok) {
  return ok ? "badge badge-success" : "badge badge-danger";
}

function confidenceClass(value) {
  const v = String(value || "").toLowerCase();
  if (v === "high") return "badge badge-success";
  if (v === "medium") return "badge badge-warning";
  if (v === "low") return "badge badge-danger";
  return "badge";
}

function llmBadgeClass(value) {
  if (value === true) return "badge badge-info";
  if (value === false) return "badge badge-muted";
  return "badge";
}

function statusClassFromText(status) {
  const text = String(status || "").toLowerCase();

  if (text.includes("согласовано")) return "status-pill status-approved";
  if (text.includes("замеч")) return "status-pill status-remarks";
  if (text.includes("направлено")) return "status-pill status-review";
  if (text.includes("отказ") || text.includes("отмен")) return "status-pill status-rejected";
  return "status-pill status-default";
}

function formatNow() {
  const now = new Date();
  return now.toLocaleString("ru-RU");
}

function friendlyModeName(internalMode) {
  const llmModes = new Set(["general_search", "similar", "analyze_new_task"]);
  const exactModes = new Set(["exact_search"]);
  const m = String(internalMode || "");
  if (llmModes.has(m)) return "AI Answer";
  if (exactModes.has(m)) return "Точный поиск";
  if (m) return "Аналитика";
  return "—";
}

function setButtonLoading(button, isLoading, loadingText) {
  if (!button) return;

  if (isLoading) {
    if (!button.dataset.originalText) {
      button.dataset.originalText = button.textContent;
    }
    button.textContent = loadingText;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
  }
}

function showAdminLog(message, type = "info") {
  const cls = type === "error" ? "admin-log-item error" : "admin-log-item";
  const line = `<div class="${cls}">${escapeHtml(formatNow())} — ${escapeHtml(message)}</div>`;
  els.adminLog.insertAdjacentHTML("afterbegin", line);
}

async function apiGet(url) {
  const res = await fetch(url, {
    method: "GET",
    headers: { "Accept": "application/json" },
  });

  const data = await res.json();
  if (!res.ok || data.ok === false) {
    throw new Error(data.message || `Ошибка GET ${url}`);
  }
  return data.data;
}

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
    body: JSON.stringify(body ?? {}),
  });

  const data = await res.json();
  if (!res.ok || data.ok === false) {
    throw new Error(data.message || `Ошибка POST ${url}`);
  }
  return data.data;
}

async function apiDelete(url) {
  const res = await fetch(url, {
    method: "DELETE",
    headers: { "Accept": "application/json" },
  });

  const data = await res.json();
  if (!res.ok || data.ok === false) {
    throw new Error(data.message || `Ошибка DELETE ${url}`);
  }
  return data.data;
}

// ── Sidebar / Chat sessions ─────────────────────────────────────

function toggleSidebar() {
  state.sidebarCollapsed = !state.sidebarCollapsed;
  els.sidebar.classList.toggle("sidebar--collapsed", state.sidebarCollapsed);
  els.sidebar.classList.remove("sidebar--mobile-open");
}

async function loadChatList() {
  try {
    const chats = await apiGet("/api/chats?limit=50");
    renderChatList(chats);
  } catch (_) {
    renderChatList([]);
  }
}

function renderChatList(chats) {
  if (!Array.isArray(chats) || chats.length === 0) {
    els.chatList.innerHTML = `<div class="chat-list-empty">Нет чатов</div>`;
    return;
  }

  els.chatList.innerHTML = chats.map(chat => {
    const isActive = chat.id === state.activeChatId;
    const title = chat.title || "Без названия";
    const time = chat.updated_at || "";
    return `
      <div class="chat-item ${isActive ? "active" : ""}" data-chat-id="${escapeHtml(chat.id)}">
        <button type="button" class="chat-item-open" data-chat-id="${escapeHtml(chat.id)}">
          <div class="chat-item-body">
            <div class="chat-item-title">${escapeHtml(title)}</div>
            <div class="chat-item-time">${escapeHtml(time)}</div>
          </div>
        </button>
        <button
          type="button"
          class="chat-item-delete"
          data-delete-chat-id="${escapeHtml(chat.id)}"
          data-chat-title="${escapeHtml(title)}"
          title="Удалить чат"
          aria-label="Удалить чат"
        >✕</button>
      </div>
    `;
  }).join("");
}

async function createNewChat() {
  state.activeChatId = "";
  els.queryInput.value = "";
  renderResult(null);
  renderChatThread([]);
  highlightActiveChat();
  els.queryInput.focus();
}

async function openChat(chatId) {
  state.activeChatId = chatId;
  highlightActiveChat();

  try {
    const messages = await apiGet(`/api/chats/${chatId}/messages`);
    renderChatThread(messages);
    renderResult(getLatestResultFromMessages(messages));
  } catch (err) {
    renderChatThread([]);
    renderResult(null);
  }
}

async function deleteChat(chatId, chatTitle = "") {
  const label = chatTitle ? `чат "${chatTitle}"` : "этот чат";
  const confirmed = window.confirm(`Удалить ${label}?`);
  if (!confirmed) return;

  try {
    await apiDelete(`/api/chats/${chatId}`);
  } catch (_) {}

  if (state.activeChatId === chatId) {
    state.activeChatId = "";
    renderResult(null);
    renderChatThread([]);
  }
  await loadChatList();
}

function highlightActiveChat() {
  const items = els.chatList.querySelectorAll(".chat-item");
  items.forEach(item => {
    item.classList.toggle("active", item.dataset.chatId === state.activeChatId);
  });
}

async function ensureActiveChatSession(query) {
  if (state.activeChatId) return state.activeChatId;

  const title = query.length > 60 ? query.substring(0, 60) + "…" : query;
  const chat = await apiPost("/api/chats", { title });
  state.activeChatId = chat.id;
  await loadChatList();
  return chat.id;
}

// -- Chat thread rendering -----------------------------------------------

function parseStoredResult(answerRaw) {
  const raw = String(answerRaw || "").trim();
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
  } catch (_) {}

  return {
    mode: "",
    short_answer: raw,
    confidence: "",
    used_llm: null,
    duration_ms: 0,
    evidence: [],
    limitations: [],
    applied_filters: [],
    used_issue_ids: [],
    items: [],
    tasks: [],
  };
}

function getLatestResultFromMessages(messages) {
  if (!Array.isArray(messages) || messages.length === 0) return null;

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const parsed = parseStoredResult(messages[i]?.answer_text || "");
    if (parsed) return parsed;
  }

  return null;
}

function compactTextList(values) {
  if (!Array.isArray(values)) return [];
  return values
    .map(value => String(value || "").trim())
    .filter(Boolean);
}

function buildThreadAnswerPreview(answerRaw) {
  const parsed = parseStoredResult(answerRaw);
  if (!parsed) return "";

  const lines = [];
  const shortAnswer = String(parsed.short_answer || "").trim();
  const evidence = compactTextList(parsed.evidence).slice(0, 3);
  const limitations = compactTextList(parsed.limitations).slice(0, 2);
  const usedIds = compactTextList(parsed.used_issue_ids).slice(0, 8);

  if (shortAnswer) {
    lines.push(shortAnswer);
  }

  if (evidence.length) {
    lines.push("", "Основание:");
    evidence.forEach(item => lines.push(`- ${item}`));
  }

  if (limitations.length) {
    lines.push("", "Ограничения:");
    limitations.forEach(item => lines.push(`- ${item}`));
  }

  if (usedIds.length) {
    lines.push("", `Задачи: ${usedIds.join(", ")}`);
  }

  return lines.join("\n").trim();
}

function renderChatThread(messages) {
  if (!Array.isArray(messages) || messages.length === 0) {
    els.chatThread.classList.add("hidden");
    els.chatThread.innerHTML = "";
    return;
  }

  els.chatThread.classList.remove("hidden");

  els.chatThread.innerHTML = messages.map(msg => {
    const queryText = msg.query_text || "";
    const answerRaw = msg.answer_text || "";
    const time = msg.created_at || "";
    const mode = msg.query_mode || "";
    const answerPreview = buildThreadAnswerPreview(answerRaw) || String(answerRaw || "");

    return `
      <div class="chat-msg chat-msg--user">
        <div class="chat-msg-header">
          <span class="chat-msg-role">Вы</span>
          <span class="chat-msg-time">${escapeHtml(time)}</span>
        </div>
        <div class="chat-msg-text">${escapeHtml(queryText)}</div>
      </div>
      <div class="chat-msg chat-msg--agent">
        <div class="chat-msg-header">
          <span class="chat-msg-role">Агент · ${escapeHtml(friendlyModeName(mode))}</span>
          <span class="chat-msg-time">${escapeHtml(time)}</span>
        </div>
        <div class="chat-msg-text">${escapeHtml(answerPreview)}</div>
      </div>
    `;
  }).join("");
}

// -- Status / Bootstrap --------------------------------------------------
function renderStatus(payload) {
  const status = payload?.status || payload || {};
  const html = [
    `<span class="${badgeClassByBoolean(status.prepared_data)}">Данные: ${status.prepared_data ? "OK" : "Нет"}</span>`,
    `<span class="${badgeClassByBoolean(status.index_ready)}">Индекс: ${status.index_ready ? "OK" : "Нет"}</span>`,
    `<span class="${badgeClassByBoolean(status.ollama_ready)}">Ollama: ${status.ollama_ready ? "OK" : "Нет"}</span>`,
    `<span class="badge badge-neutral">Всего задач: ${Number(status.tasks_total || 0)}</span>`,
    `<span class="badge badge-neutral">Активных: ${Number(status.active_total || 0)}</span>`,
    `<span class="badge badge-neutral">Финальных: ${Number(status.final_total || 0)}</span>`,
    `<span class="badge badge-warning">Просрочено: ${Number(status.overdue_total || 0)}</span>`,
    `<span class="badge badge-info">С замечаниями: ${Number(status.with_remarks_total || 0)}</span>`,
    `<span class="badge badge-info">Ожид. согласований: ${Number(status.pending_approvals_total || 0)}</span>`,
  ].join("");

  els.statusBadges.innerHTML = html;
  els.statusUpdatedAt.textContent = `Обновлено: ${formatNow()}`;
}

function renderExampleCategories(categories) {
  if (!Array.isArray(categories)) {
    els.exampleCategories.innerHTML = "";
    els.exampleExamples.innerHTML = "";
    return;
  }

  els.exampleCategories.innerHTML = categories.map((category, index) => `
    <button
      type="button"
      class="example-category-btn ${index === 0 ? "active" : ""}"
      data-category-id="${escapeHtml(category.id)}"
    >
      ${escapeHtml(category.title)}
    </button>
  `).join("");

  const first = categories[0];
  state.selectedExampleCategoryId = first?.id || null;
  renderExampleExamples(first?.examples || []);
}

function renderExampleExamples(examples) {
  if (!Array.isArray(examples) || examples.length === 0) {
    els.exampleExamples.innerHTML = `<div class="muted">Нет примеров</div>`;
    return;
  }

  els.exampleExamples.innerHTML = examples.map(example => `
    <button type="button" class="example-chip" data-example="${escapeHtml(example)}">
      ${escapeHtml(example)}
    </button>
  `).join("");
}

function selectCategoryButton(categoryId) {
  const buttons = els.exampleCategories.querySelectorAll(".example-category-btn");
  buttons.forEach(button => {
    button.classList.toggle("active", button.dataset.categoryId === categoryId);
  });
}

function getTasksFromResult(result) {
  if (!result) return [];
  const tasks = Array.isArray(result.tasks) ? [...result.tasks] : [];
  if (result.task && !tasks.length) {
    tasks.push(result.task);
  }
  return tasks;
}

function renderSimpleList(container, values, emptyText) {
  if (!Array.isArray(values) || values.length === 0) {
    container.innerHTML = `<li class="muted">${escapeHtml(emptyText)}</li>`;
    return;
  }

  container.innerHTML = values.map(value => `<li>${escapeHtml(value)}</li>`).join("");
}

function renderTaskCards(tasks) {
  if (!Array.isArray(tasks) || tasks.length === 0) {
    els.tasksBlock.classList.add("hidden");
    els.tasksContainer.innerHTML = "";
    return;
  }

  els.tasksBlock.classList.remove("hidden");

  els.tasksContainer.innerHTML = tasks.map(task => {
    const issueId = task.issue_id || "";
    const summary = task.summary || "";
    const status = task.status || "";
    const priority = task.priority || "";
    const customer = task.functional_customer || "";
    const responsible = task.responsible_dit || "";
    const stage = task.current_approval_stage || "";
    const overdue = Boolean(task.is_overdue);
    const overdueDays = Number(task.overdue_days || 0);
    const pendingApprovals = Array.isArray(task.pending_approvals) ? task.pending_approvals.join(", ") : "";
    const mainDeadline = task.main_deadline?.value || "";
    const mainDeadlineLabel = task.main_deadline?.label || "";

    return `
      <div class="task-card">
        <div class="task-card-top">
          <div>
            <div class="task-id">${escapeHtml(issueId)}</div>
            <div class="task-title">${escapeHtml(summary)}</div>
          </div>
          <div class="task-badges">
            <span class="${statusClassFromText(status)}">${escapeHtml(status || "Без статуса")}</span>
            ${priority ? `<span class="badge badge-neutral">${escapeHtml(priority)}</span>` : ""}
            ${overdue ? `<span class="badge badge-warning">Просрочка: ${overdueDays} дн.</span>` : ""}
          </div>
        </div>

        <div class="task-meta-grid">
          <div class="task-meta-item">
            <span class="task-meta-label">Заказчик</span>
            <span>${escapeHtml(customer || "—")}</span>
          </div>
          <div class="task-meta-item">
            <span class="task-meta-label">Ответственный</span>
            <span>${escapeHtml(responsible || "—")}</span>
          </div>
          <div class="task-meta-item">
            <span class="task-meta-label">Текущая стадия</span>
            <span>${escapeHtml(stage || "—")}</span>
          </div>
          <div class="task-meta-item">
            <span class="task-meta-label">Ожидаемые согласования</span>
            <span>${escapeHtml(pendingApprovals || "—")}</span>
          </div>
          <div class="task-meta-item full">
            <span class="task-meta-label">Ближайший дедлайн</span>
            <span>${escapeHtml(mainDeadline ? `${mainDeadlineLabel}: ${mainDeadline}` : "—")}</span>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

function renderItems(result) {
  const items = Array.isArray(result?.items) ? result.items : [];
  const mode = String(result?.mode || "");

  if (!items.length) {
    els.itemsBlock.classList.add("hidden");
    els.itemsContainer.innerHTML = "";
    return;
  }

  els.itemsBlock.classList.remove("hidden");

  if (mode === "count" || mode === "stats") {
    els.itemsContainer.innerHTML = `
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Значение</th>
              <th>Количество</th>
            </tr>
          </thead>
          <tbody>
            ${items.map(item => {
              const name = Array.isArray(item) ? item[0] : item?.name;
              const count = Array.isArray(item) ? item[1] : item?.count;
              return `
                <tr>
                  <td>${escapeHtml(name)}</td>
                  <td>${Number(count || 0)}</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    `;
    return;
  }

  if (mode === "overdue" || mode === "deadlines") {
    els.itemsContainer.innerHTML = `
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Срок</th>
              <th>Дата</th>
              <th>Статус</th>
              <th>Ответственный</th>
              <th>${mode === "overdue" ? "Просрочка" : "Осталось"}</th>
            </tr>
          </thead>
          <tbody>
            ${items.map(item => `
              <tr>
                <td>${escapeHtml(item.issue_id)}</td>
                <td>${escapeHtml(item.deadline_label || item.deadline_field || "")}</td>
                <td>${escapeHtml(item.deadline_value || "")}</td>
                <td>${escapeHtml(item.status || "")}</td>
                <td>${escapeHtml(item.responsible_dit || "")}</td>
                <td>${mode === "overdue"
                  ? `${Number(item.overdue_days || 0)} дн.`
                  : (item.days_to_deadline !== null && item.days_to_deadline !== undefined
                      ? `${Number(item.days_to_deadline)} дн.`
                      : "—")
                }</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
    return;
  }

  els.itemsContainer.innerHTML = `
    <pre class="json-view">${escapeHtml(JSON.stringify(items, null, 2))}</pre>
  `;
}

function renderResult(result) {
  state.lastResult = result || null;

  if (!result) {
    els.resultEmpty.classList.remove("hidden");
    els.resultContent.classList.add("hidden");
    els.exportBtn.disabled = true;
    return;
  }

  els.resultEmpty.classList.add("hidden");
  els.resultContent.classList.remove("hidden");
  els.exportBtn.disabled = false;

  els.resultMeta.textContent = `Режим: ${friendlyModeName(result.mode)} • Время: ${Number(result.duration_ms || 0)} мс`;

  els.shortAnswer.textContent = result.short_answer || "";

  els.confidenceBadge.className = confidenceClass(result.confidence);
  els.confidenceBadge.textContent = `Уверенность: ${result.confidence || "—"}`;

  els.llmBadge.className = llmBadgeClass(result.used_llm);
  els.llmBadge.textContent = result.used_llm === true ? "Через LLM" : "Без LLM";

  renderSimpleList(els.evidenceList, result.evidence, "Нет фактов");
  renderSimpleList(els.limitationsList, result.limitations, "Нет ограничений");
  const appliedFilters = Array.isArray(result.applied_filters)
    ? result.applied_filters.map(normalizeFilterLabel)
    : [];
  renderSimpleList(els.filtersList, appliedFilters, "Нет фильтров");
  renderSimpleList(els.usedIdsList, result.used_issue_ids, "Нет использованных ID");

  renderItems(result);
  renderTaskCards(getTasksFromResult(result));
}

// ── Bootstrap ───────────────────────────────────────────────────

async function loadBootstrap() {
  const data = await apiGet("/api/ui-bootstrap");
  state.bootstrap = data;

  renderStatus(data);
  renderExampleCategories(data.examples || []);

  if (!state.selectedExampleCategoryId && Array.isArray(data.examples) && data.examples[0]) {
    state.selectedExampleCategoryId = data.examples[0].id;
  }
}

// ── Suggestions ─────────────────────────────────────────────────

function openSuggestions() {
  els.suggestionsBox.classList.remove("hidden");
}

function closeSuggestions() {
  els.suggestionsBox.classList.add("hidden");
}

function renderSuggestions(items) {
  if (!Array.isArray(items) || items.length === 0) {
    els.suggestionsBox.innerHTML = "";
    closeSuggestions();
    return;
  }

  els.suggestionsBox.innerHTML = items.map(item => `
    <button
      type="button"
      class="suggestion-item"
      data-insert-text="${escapeHtml(item.insert_text)}"
    >
      <span class="suggestion-type">${escapeHtml(item.type || "suggestion")}</span>
      <span class="suggestion-label">${escapeHtml(item.label || item.insert_text || "")}</span>
    </button>
  `).join("");

  openSuggestions();
}

async function fetchSuggestions(query) {
  const data = await apiGet(`/api/suggestions?q=${encodeURIComponent(query)}&limit=8`);
  renderSuggestions(data);
}

function scheduleSuggestions() {
  clearTimeout(state.suggestionTimer);

  const query = els.queryInput.value.trim();

  state.suggestionTimer = setTimeout(async () => {
    try {
      await fetchSuggestions(query);
    } catch (_) {
      closeSuggestions();
    }
  }, 220);
}

// ── Query execution ─────────────────────────────────────────────

function showProgress(text = "Обработка запроса…") {
  state.streamBuffer = "";
  els.progressText.textContent = text;
  els.progressBox.classList.remove("hidden");
}

function hideProgress() {
  els.progressBox.classList.add("hidden");
}

function setQueryRunning(isRunning) {
  els.runQueryBtn.disabled = isRunning;
  els.stopQueryBtn.disabled = !isRunning;
  els.exportBtn.disabled = isRunning || !state.lastResult;
}

function parseSseChunks(buffer) {
  const parts = buffer.split("\n\n");
  const completeEvents = parts.slice(0, -1);
  const remainder = parts.slice(-1)[0] || "";
  return { completeEvents, remainder };
}

function parseSingleSseEvent(rawEvent) {
  const lines = rawEvent.split("\n");
  let eventName = "message";
  const dataLines = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  const dataText = dataLines.join("\n");
  let data = {};
  if (dataText) {
    try {
      data = JSON.parse(dataText);
    } catch (_) {
      data = { raw: dataText };
    }
  }

  return { eventName, data };
}

async function runQueryStream() {
  const query = els.queryInput.value.trim();
  const mode = state.selectedMode;

  if (!query) {
    alert("Введите запрос.");
    return;
  }

  if (state.abortController) {
    state.abortController.abort();
  }

  let chatId;
  try {
    chatId = await ensureActiveChatSession(query);
  } catch (err) {
    chatId = "";
  }

  state.abortController = new AbortController();
  state.lastResult = null;
  setQueryRunning(true);
  renderResult(null);
  showProgress();

  try {
    const response = await fetch("/api/query-stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
      },
      body: JSON.stringify({ query, mode, chat_id: chatId }),
      signal: state.abortController.signal,
    });

    if (!response.ok || !response.body) {
      throw new Error("Ответ сервера недоступен.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let textBuffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      textBuffer += decoder.decode(value, { stream: true });

      const { completeEvents, remainder } = parseSseChunks(textBuffer);
      textBuffer = remainder;

      for (const rawEvent of completeEvents) {
        const { eventName, data } = parseSingleSseEvent(rawEvent);

        if (eventName === "token") {
          state.streamBuffer += String(data.text || "");
        } else if (eventName === "result") {
          hideProgress();
          renderResult(data);
        } else if (eventName === "done") {
          hideProgress();
        }
      }
    }

    if (!state.lastResult) {
      const data = await apiPost("/api/query", { query, mode, chat_id: chatId });
      hideProgress();
      renderResult(data);
    }
  } catch (error) {
    hideProgress();

    if (error.name === "AbortError") {
      return;
    }

    try {
      const data = await apiPost("/api/query", { query, mode, chat_id: chatId });
      renderResult(data);
    } catch (fallbackError) {
      alert(`Ошибка запроса: ${fallbackError.message || error.message}`);
    }
  } finally {
    setQueryRunning(false);
    state.abortController = null;

    try { await loadChatList(); } catch (_) {}
  }
}

function stopQuery() {
  if (state.abortController) {
    state.abortController.abort();
  }
}

async function exportCurrentResult() {
  const query = els.queryInput.value.trim();
  const mode = state.selectedMode;

  if (!query) {
    alert("Сначала введи запрос.");
    return;
  }

  try {
    setButtonLoading(els.exportBtn, true, "Экспорт...");
    const response = await fetch("/api/export-results", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, mode }),
    });

    if (!response.ok) {
      throw new Error("Не удалось выгрузить CSV.");
    }

    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="(.+?)"/);
    const filename = match ? match[1] : "agent_export.csv";

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    alert(error.message || "Ошибка экспорта.");
  } finally {
    setButtonLoading(els.exportBtn, false, "Экспорт CSV");
  }
}

// ── Admin actions ───────────────────────────────────────────────

async function runPrepare() {
  try {
    setButtonLoading(els.prepareBtn, true, "Подготовка...");
    const data = await apiPost("/api/prepare", {});
    showAdminLog(`Подготовка данных завершена. Всего задач: ${Number(data.tasks_total || 0)}`);
    await loadBootstrap();
  } catch (error) {
    showAdminLog(error.message || "Ошибка подготовки данных", "error");
  } finally {
    setButtonLoading(els.prepareBtn, false, "Подготовить данные");
  }
}

async function runRebuild() {
  try {
    setButtonLoading(els.rebuildBtn, true, "Пересборка...");
    const data = await apiPost("/api/rebuild-index", {});
    showAdminLog(`Индекс пересобран: ${JSON.stringify(data)}`);
    await loadBootstrap();
  } catch (error) {
    showAdminLog(error.message || "Ошибка пересборки индекса", "error");
  } finally {
    setButtonLoading(els.rebuildBtn, false, "Пересобрать индекс");
  }
}

function setMode(mode) {
  state.selectedMode = mode;
  els.modeAiBtn.classList.toggle("active", mode === "ai_answer");
  els.modePreciseBtn.classList.toggle("active", mode === "precise");
}

// ── Events ──────────────────────────────────────────────────────

function bindEvents() {
  try {
  els.modeAiBtn.addEventListener("click", () => setMode("ai_answer"));
  els.modePreciseBtn.addEventListener("click", () => setMode("precise"));

  els.adminToggleBtn.addEventListener("click", () => {
    els.adminSection.classList.toggle("hidden");
    const open = !els.adminSection.classList.contains("hidden");
    els.adminToggleBtn.textContent = open
      ? "Сервисные действия ▴"
      : "Сервисные действия ▾";
  });

  els.refreshBootstrapBtn.addEventListener("click", async () => {
    try {
      await loadBootstrap();
      showAdminLog("UI bootstrap обновлен");
    } catch (error) {
      showAdminLog(error.message || "Ошибка обновления UI bootstrap", "error");
    }
  });

  els.runQueryBtn.addEventListener("click", runQueryStream);
  els.stopQueryBtn.addEventListener("click", stopQuery);
  els.exportBtn.addEventListener("click", exportCurrentResult);

  els.prepareBtn.addEventListener("click", runPrepare);
  els.rebuildBtn.addEventListener("click", runRebuild);

  els.sidebarToggleBtn.addEventListener("click", toggleSidebar);
  els.newChatBtn.addEventListener("click", createNewChat);

  els.queryInput.addEventListener("input", scheduleSuggestions);

  els.queryInput.addEventListener("focus", () => {
    scheduleSuggestions();
  });

  els.queryInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      runQueryStream();
    }
  });

  document.addEventListener("click", (event) => {
    const target = event.target;

    if (target.closest(".chat-item-delete")) {
      const btn = target.closest(".chat-item-delete");
      const chatId = btn.dataset.deleteChatId;
      const chatTitle = btn.dataset.chatTitle || "";
      if (chatId) {
        event.stopPropagation();
        deleteChat(chatId, chatTitle);
      }
      return;
    }

    if (target.closest(".chat-item-open")) {
      const item = target.closest(".chat-item-open");
      const chatId = item.dataset.chatId;
      if (chatId) openChat(chatId);
      return;
    }

    if (target.closest(".suggestion-item")) {
      const button = target.closest(".suggestion-item");
      const insertText = button.dataset.insertText || "";
      els.queryInput.value = insertText;
      closeSuggestions();
      els.queryInput.focus();
      return;
    }

    if (target.closest(".example-category-btn")) {
      const button = target.closest(".example-category-btn");
      const categoryId = button.dataset.categoryId;
      const categories = state.bootstrap?.examples || [];
      const category = categories.find(item => item.id === categoryId);

      state.selectedExampleCategoryId = categoryId;
      selectCategoryButton(categoryId);
      renderExampleExamples(category?.examples || []);
      return;
    }

    if (target.closest(".example-chip")) {
      const button = target.closest(".example-chip");
      const example = button.dataset.example || "";
      els.queryInput.value = example;
      els.queryInput.focus();
      return;
    }

    if (
      !target.closest(".query-input-wrap") &&
      !target.closest(".suggestions")
    ) {
      closeSuggestions();
    }
  });
  } catch (e) {
    console.error("bindEvents error:", e);
  }
}

// ── Init ────────────────────────────────────────────────────────

async function init() {
  els.refreshBootstrapBtn = document.getElementById("refreshBootstrapBtn");
  els.statusUpdatedAt = document.getElementById("statusUpdatedAt");
  els.statusBadges = document.getElementById("statusBadges");

  els.modeAiBtn = document.getElementById("modeAiBtn");
  els.modePreciseBtn = document.getElementById("modePreciseBtn");

  els.queryInput = document.getElementById("queryInput");
  els.runQueryBtn = document.getElementById("runQueryBtn");
  els.stopQueryBtn = document.getElementById("stopQueryBtn");
  els.exportBtn = document.getElementById("exportBtn");

  els.suggestionsBox = document.getElementById("suggestionsBox");

  els.progressBox = document.getElementById("progressBox");
  els.progressText = document.getElementById("progressText");

  els.exampleCategories = document.getElementById("exampleCategories");
  els.exampleExamples = document.getElementById("exampleExamples");

  els.resultMeta = document.getElementById("resultMeta");
  els.resultEmpty = document.getElementById("resultEmpty");
  els.resultContent = document.getElementById("resultContent");

  els.shortAnswer = document.getElementById("shortAnswer");
  els.confidenceBadge = document.getElementById("confidenceBadge");
  els.llmBadge = document.getElementById("llmBadge");
  els.evidenceList = document.getElementById("evidenceList");
  els.limitationsList = document.getElementById("limitationsList");
  els.filtersList = document.getElementById("filtersList");
  els.usedIdsList = document.getElementById("usedIdsList");

  els.itemsBlock = document.getElementById("itemsBlock");
  els.itemsContainer = document.getElementById("itemsContainer");
  els.tasksBlock = document.getElementById("tasksBlock");
  els.tasksContainer = document.getElementById("tasksContainer");

  els.adminToggleBtn = document.getElementById("adminToggleBtn");
  els.adminSection = document.getElementById("adminSection");
  els.prepareBtn = document.getElementById("prepareBtn");
  els.rebuildBtn = document.getElementById("rebuildBtn");
  els.adminLog = document.getElementById("adminLog");

  els.sidebar = document.getElementById("sidebar");
  els.sidebarToggleBtn = document.getElementById("sidebarToggleBtn");
  els.newChatBtn = document.getElementById("newChatBtn");
  els.chatList = document.getElementById("chatList");
  els.chatThread = document.getElementById("chatThread");

  bindEvents();
  renderResult(null);

  try {
    await loadBootstrap();
  } catch (error) {
    const msg = error.message || "Ошибка загрузки данных";
    showAdminLog(msg, "error");
    if (els.resultEmpty) {
      els.resultEmpty.textContent = `Данные не загружены: ${msg}. Откройте «Сервисные действия» и нажмите «Подготовить данные».`;
    }
  }

  try {
    await loadChatList();
  } catch (_) {}
}

window.addEventListener("DOMContentLoaded", init);

