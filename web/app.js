const body = document.body;
const page = body.dataset.page || "dashboard";

const form = document.querySelector("#config-form");
const actionOutput = document.querySelector("#action-output");
const logsOutput = document.querySelector("#logs-output");
const scriptOutput = document.querySelector("#script-output");
const resourceEditor = document.querySelector("#resource-editor");
const vpnOutput = document.querySelector("#vpn-output");
const vpnLocationSelect = document.querySelector("#vpn-location-select");
const autostartOutput = document.querySelector("#autostart-output");

const fields = [
  "automation.enabled",
  "automation.check_interval",
  "vpn.test_url",
  "vpn.expected_text",
  "vpn.top_count",
  "vpn.timeout",
  "vpn.connect_timeout",
  "vpn.check_retries",
  "vpn.check_retry_delay",
  "vpn.switch_delay",
  "panel.host",
  "panel.port",
  "panel.script_runner",
  "panel.source_script",
  "panel.generated_script",
  "adguardvpn.cli_command",
  "adguardvpn.command_timeout",
  "adguardvpn.locations_limit",
  "autostart.enabled",
  "autostart.service_name",
  "autostart.app_dir",
  "autostart.python_bin",
  "autostart.log_file",
  "autostart.pid_file",
  "autostart.start_script_path",
  "autostart.init_script_path",
  "paths.lock_file",
  "paths.log_file",
  "paths.good_file",
  "paths.tmp_file",
  "paths.body_file",
  "logging.debug_enabled",
  "logging.debug_log_file",
  "logging.debug_max_bytes",
  "logging.debug_backup_count",
];

function byId(id) {
  return document.getElementById(id);
}

function setConsole(element, payload) {
  if (!element) {
    return;
  }
  element.textContent =
    typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
}

function setStatusMessage(message) {
  setConsole(actionOutput, message);
}

function setVpnMessage(message) {
  setConsole(vpnOutput, message);
}

function setAutostartMessage(message) {
  setConsole(autostartOutput, message);
}

function setText(id, value) {
  const element = byId(id);
  if (element) {
    element.textContent = value;
  }
}

function setFieldValue(name, value) {
  if (!form) {
    return;
  }
  const input = form.elements.namedItem(name);
  if (input) {
    if (input.type === "checkbox") {
      input.checked = Boolean(value);
    } else {
      input.value = value ?? "";
    }
  }
}

function normalizeResource(resource = {}, index = 0) {
  return {
    name: resource.name ?? "",
    url: resource.url ?? "",
    description: resource.description ?? "",
    group: resource.group ?? "",
    index,
  };
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

function getHostLabel(url) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function formatExists(item) {
  if (!item) {
    return "-";
  }
  return item.exists ? item.path : `${item.path} (не найден)`;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }

  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return [
      parsed.getFullYear(),
      pad2(parsed.getMonth() + 1),
      pad2(parsed.getDate()),
    ].join("-") + ` ${pad2(parsed.getHours())}:${pad2(parsed.getMinutes())}:${pad2(parsed.getSeconds())}`;
  }

  return String(value)
    .replace("T", " ")
    .replace(/\.\d+/, "")
    .replace(/[+-]\d\d:\d\d$/, "")
    .replace(/Z$/, "");
}

function renderSummary(record, successText, emptyText) {
  if (!record) {
    return emptyText;
  }

  const stamp = formatDateTime(
    record.checked_at || record.executed_at || record.generated_at || "-"
  );
  const label =
    record.success === undefined ? "OK" : record.success ? successText : "Ошибка";
  const message = record.message || "";
  return `${label} • ${stamp}${message ? ` • ${message}` : ""}`;
}

function highlightActiveNav() {
  for (const link of document.querySelectorAll("[data-nav]")) {
    link.classList.toggle("active", link.dataset.nav === page);
  }
}

function updateResourceCounters(count) {
  setText("sidebar-resource-count", String(count));
  setText("aside-resource-count", String(count));
}

function renderSidebarResources(resources) {
  const container = byId("sidebar-resource-links");
  if (!container) {
    return;
  }

  if (!resources.length) {
    container.innerHTML =
      '<div class="sidebar-resource-empty">Ссылки ещё не добавлены.</div>';
    updateResourceCounters(0);
    return;
  }

  container.innerHTML = resources
    .map((item, index) => {
      const resource = normalizeResource(item, index);
      const name = resource.name || `Ресурс ${index + 1}`;
      const group = resource.group || "LAN";
      const description = resource.description || getHostLabel(resource.url);
      return `
        <a class="sidebar-resource-link" href="${escapeAttribute(
          resource.url
        )}" target="_blank" rel="noreferrer">
          <strong>${escapeHtml(name)}</strong>
          <span>${escapeHtml(group)} • ${escapeHtml(description)}</span>
        </a>
      `;
    })
    .join("");

  updateResourceCounters(resources.length);
}

function renderResourceEditor(resources) {
  if (!resourceEditor) {
    return;
  }

  const list = resources.length ? resources : [normalizeResource({}, 0)];
  resourceEditor.innerHTML = list
    .map((item, index) => {
      const resource = normalizeResource(item, index);
      return `
        <article class="resource-row">
          <div class="resource-row-grid">
            <label>
              Название
              <input data-field="name" type="text" value="${escapeAttribute(
                resource.name
              )}" />
            </label>
            <label>
              URL
              <input data-field="url" type="url" value="${escapeAttribute(
                resource.url
              )}" />
            </label>
            <label>
              Группа
              <input data-field="group" type="text" value="${escapeAttribute(
                resource.group
              )}" />
            </label>
            <label>
              Описание
              <input data-field="description" type="text" value="${escapeAttribute(
                resource.description
              )}" />
            </label>
          </div>
          <div class="resource-row-actions">
            <button class="ghost small remove-resource" type="button">Удалить</button>
          </div>
        </article>
      `;
    })
    .join("");
}

function getResourcesFromEditor() {
  if (!resourceEditor) {
    return [];
  }

  return [...resourceEditor.querySelectorAll(".resource-row")]
    .map((row, index) => {
      const resource = {
        name: row.querySelector('[data-field="name"]').value.trim(),
        url: row.querySelector('[data-field="url"]').value.trim(),
        description: row.querySelector('[data-field="description"]').value.trim(),
        group: row.querySelector('[data-field="group"]').value.trim(),
      };

      if (!resource.name && !resource.url && !resource.description && !resource.group) {
        return null;
      }

      return normalizeResource(resource, index);
    })
    .filter(Boolean);
}

function syncSidebarResourcesFromEditor() {
  if (!resourceEditor) {
    return;
  }
  renderSidebarResources(getResourcesFromEditor());
}

function buildConfigFromForm() {
  const config = {
    panel: {},
    vpn: {},
    adguardvpn: {},
    automation: {},
    autostart: {},
    paths: {},
    logging: {},
    resources: { links: [] },
  };

  for (const field of fields) {
    const [section, key] = field.split(".");
    const input = form.elements.namedItem(field);
    const rawValue = input.type === "checkbox" ? input.checked : input.value.trim();
    config[section][key] =
      input.type === "number" ? Number(rawValue) : rawValue;
  }

  config.resources.links = getResourcesFromEditor();
  return config;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

async function saveCurrentConfig(showMessage = true) {
  if (!form) {
    return null;
  }
  const result = await fetchJson("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildConfigFromForm()),
  });
  if (showMessage) {
    setStatusMessage(
      `Настройки сохранены.\n\n${JSON.stringify(result, null, 2)}`
    );
  }
  await Promise.all([loadConfig(), loadState()]);
  return result;
}

function fillConfig(config) {
  for (const field of fields) {
    const [section, key] = field.split(".");
    setFieldValue(field, config[section]?.[key]);
  }

  const resources = config.resources?.links ?? [];
  renderResourceEditor(resources);
  renderSidebarResources(resources);
}

async function loadConfig() {
  const config = await fetchJson("/api/config");
  fillConfig(config);
}

async function loadState() {
  const state = await fetchJson("/api/state");
  const automation = state.automation || {};

  setText("source-script", formatExists(state.source_script));
  setText("generated-script", formatExists(state.generated_script));
  setText("log-file", formatExists(state.log_file));
  setText("last-good-location", state.last_good_location || "Нет данных");
  setText("sidebar-last-good-location", state.last_good_location || "Нет данных");
  setText("last-check-summary", renderSummary(state.last_check, "Успех", "Нет данных"));
  setText(
    "last-rotation-summary",
    renderSummary(state.last_rotation, "Успех", "Нет данных")
  );
  setText(
    "last-generation-summary",
    renderSummary(state.last_script_generation, "Готово", "Нет данных")
  );
  setText(
    "last-update-summary",
    renderSummary(state.last_update_action, "Успех", "Нет данных")
  );
  setText("automation-status-summary", formatAutomationStatus(automation));
  setText("automation-next-check", formatAutomationNextCheck(automation));
  setText(
    "automation-last-action",
    renderSummary(state.last_automation_action, "Успех", "Нет данных")
  );
  setText("panel-url", state.panel_url || "-");
  setText("sidebar-panel-url", state.panel_url || "-");
  setText("aside-panel-url", state.panel_url || "-");
  setText("config-path", state.config_path || "-");
  updateResourceCounters(state.resource_count ?? 0);
  setText(
    "vpn-last-action",
    renderSummary(state.last_cli_action, "Успех", "Нет данных")
  );
  setText(
    "autostart-last-action",
    renderSummary(state.last_autostart_action, "Успех", "Нет данных")
  );
  updateAutomationToggle(automation);
}

function formatAutomationStatus(status) {
  if (!status || status.enabled === undefined) {
    return "Нет данных";
  }
  if (!status.enabled) {
    return "Выключен";
  }
  if (status.loop_running) {
    return `Проверка выполняется • ${status.check_interval} сек`;
  }
  if (status.last_error) {
    return `Ошибка • ${status.last_error}`;
  }
  return `Включён • ${status.check_interval} сек`;
}

function formatAutomationNextCheck(status) {
  if (!status || !status.enabled) {
    return "Авто-режим выключен";
  }
  if (status.loop_running) {
    return "Выполняется сейчас";
  }
  return status.next_check_at
    ? formatDateTime(status.next_check_at)
    : "Ожидание первого цикла";
}

function updateAutomationToggle(status) {
  const button = byId("automation-toggle");
  if (!button) {
    return;
  }
  button.textContent = status?.enabled ? "Выключить авто-режим" : "Включить авто-режим";
}

function renderVpnStatus(status) {
  setText("vpn-cli-availability", status.available ? "Доступен" : "Недоступен");
  setText(
    "vpn-connected-status",
    status.available ? (status.connected ? "Подключено" : "Не подключено") : "-"
  );
  setText("vpn-current-location", status.location || "Нет данных");
  if (status.location) {
    setText("last-good-location", status.location);
    setText("sidebar-last-good-location", status.location);
  }
}

function renderVpnLocations(payload) {
  if (!vpnLocationSelect) {
    return;
  }

  const items = payload.items || [];
  vpnLocationSelect.innerHTML =
    '<option value="">Quick connect</option>' +
    items
      .map((item) => {
        const title = [item.code, item.country, item.city].filter(Boolean).join(" • ");
        return `<option value="${escapeAttribute(item.code)}">${escapeHtml(title)}</option>`;
      })
      .join("");
}

async function loadVpnStatus() {
  if (!vpnOutput && !byId("vpn-cli-availability")) {
    return;
  }
  const status = await fetchJson("/api/adguardvpn/status");
  renderVpnStatus(status);
  return status;
}

async function loadVpnLocations() {
  if (!vpnLocationSelect) {
    return;
  }
  const locations = await fetchJson("/api/adguardvpn/locations");
  renderVpnLocations(locations);
  return locations;
}

async function loadAutostartStatus() {
  if (!autostartOutput) {
    return;
  }
  const status = await fetchJson("/api/autostart/status");
  setAutostartMessage(JSON.stringify(status, null, 2));
  return status;
}

async function toggleAutomationMode() {
  const currentConfig = await fetchJson("/api/config");
  const enabled = !Boolean(currentConfig.automation?.enabled);
  const intervalInput = form?.elements?.namedItem("automation.check_interval");
  const interval = Number(intervalInput?.value || currentConfig.automation?.check_interval) || 600;
  const result = await fetchJson("/api/automation/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled, check_interval: interval }),
  });
  await Promise.all([loadConfig(), loadState(), loadLogs()]);
  return result;
}

async function runVpnAction(url, payload, successPrefix, failurePrefix) {
  setVpnMessage("Выполняется...");
  const result = await fetchJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const status = result.status || result;
  const prefix = result.success === false
    ? (failurePrefix || "Команда завершилась с ошибкой.")
    : successPrefix;
  const summary = [prefix, "", formatVpnStatusText(status)];
  if (result.stdout || result.stderr) {
    summary.push("", "CLI output:");
    if (result.stdout) {
      summary.push(result.stdout.trim());
    }
    if (result.stderr) {
      summary.push(result.stderr.trim());
    }
  }
  setVpnMessage(summary.filter(Boolean).join("\n"));
  await Promise.all([loadState(), loadVpnStatus(), loadVpnLocations()]);
}

function formatVpnStatusText(status) {
  const lines = [];
  lines.push(`CLI: ${status.available ? "доступен" : "недоступен"}`);
  lines.push(`Команда: ${status.command?.join(" ") || "-"}`);
  if (status.returncode !== null && status.returncode !== undefined) {
    lines.push(`Код возврата: ${status.returncode}`);
  }
  lines.push(`Статус: ${status.connected ? "подключено" : "не подключено"}`);
  lines.push(`Локация: ${status.location || "не определена"}`);
  if (status.mode) {
    lines.push(`Режим: ${status.mode}`);
  }
  if (status.listener) {
    lines.push(`Слушает: ${status.listener}`);
  }
  if (status.message) {
    lines.push(`Сообщение: ${status.message}`);
  }
  if (status.stderr) {
    lines.push(`stderr: ${status.stderr.trim()}`);
  }
  const statusOutput = (status.clean_raw || status.raw || "").trim();
  if (statusOutput && !status.command_success) {
    lines.push(`stdout: ${statusOutput}`);
  }
  return lines.join("\n");
}

function formatVpnLocationsText(payload) {
  const items = payload.items || [];
  const lines = [];
  lines.push(`CLI: ${payload.available ? "доступен" : "недоступен"}`);
  if (payload.returncode !== null && payload.returncode !== undefined) {
    lines.push(`Код возврата: ${payload.returncode}`);
  }
  lines.push(`Локаций найдено: ${items.length}`);
  if (payload.message) {
    lines.push(`Сообщение: ${payload.message}`);
  }
  if (!items.length) {
    if (payload.stderr) {
      lines.push(`stderr: ${payload.stderr.trim()}`);
    }
    const locationsOutput = (payload.clean_raw || payload.raw || "").trim();
    if (locationsOutput) {
      lines.push(`stdout: ${locationsOutput}`);
    }
    return lines.join("\n");
  }

  lines.push("");
  items.forEach((item, index) => {
    lines.push(
      `${String(index + 1).padStart(2, "0")}. ${item.code} | ${item.country} | ${item.city} | ping ${item.score}`
    );
  });
  return lines.join("\n");
}

async function runAutostartAction(url, payload, successPrefix) {
  setAutostartMessage("Выполняется...");
  const result = await fetchJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  setAutostartMessage(`${successPrefix}\n\n${JSON.stringify(result, null, 2)}`);
  await Promise.all([loadState(), loadAutostartStatus()]);
}

async function loadLogs() {
  if (!logsOutput) {
    return;
  }
  const logs = await fetchJson("/api/logs");
  const sections = [];
  sections.push(
    logs.exists
      ? `Основной лог: ${logs.path}\n\n${logs.content || "Лог-файл пуст."}`
      : `Основной лог не найден: ${logs.path}`
  );
  if (logs.debug) {
    const debugHeader = logs.debug.enabled
      ? `Debug-лог: ${logs.debug.path}`
      : `Debug-лог отключён: ${logs.debug.path}`;
    const debugBody = logs.debug.exists
      ? logs.debug.content || "Debug-лог пуст."
      : "Файл debug-лога не найден.";
    sections.push(`${debugHeader}\n\n${debugBody}`);
  }
  setConsole(
    logsOutput,
    sections.join("\n\n====================\n\n")
  );
}

async function loadScript() {
  if (!scriptOutput) {
    return;
  }
  const script = await fetchJson("/api/script");
  setConsole(scriptOutput, script.content);
}

async function runAction(url, successPrefix) {
  setStatusMessage("Выполняется...");
  const result = await fetchJson(url, { method: "POST" });
  if (actionOutput) {
    setConsole(
      actionOutput,
      `${successPrefix}\n\n${JSON.stringify(result, null, 2)}`
    );
  }
  await Promise.all([loadState(), loadLogs(), loadScript(), loadVpnStatus()]);
}

async function waitForPanelAndReload(delaySeconds = 4) {
  const initialDelay = Math.max(1000, Number(delaySeconds || 4) * 1000);
  await new Promise((resolve) => window.setTimeout(resolve, initialDelay));

  for (let attempt = 1; attempt <= 12; attempt += 1) {
    try {
      const response = await fetch(`/api/state?_=${Date.now()}`, { cache: "no-store" });
      if (response.ok) {
        window.location.reload();
        return;
      }
    } catch {
      // Панель ещё перезапускается, продолжаем ждать.
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }
}

async function runProjectUpdateFlow(setMessage) {
  setMessage("Запускаю обновление с GitHub...");
  const result = await fetchJson("/api/actions/update-project", { method: "POST" });
  setMessage(JSON.stringify(result, null, 2));

  if (result.restart_scheduled) {
    waitForPanelAndReload((result.restart_delay_seconds || 2) + 2);
    return result;
  }

  await Promise.all([loadState(), loadLogs(), loadScript(), loadVpnStatus(), loadAutostartStatus()]);
  return result;
}

function bindClick(id, handler) {
  const element = byId(id);
  if (element) {
    element.addEventListener("click", handler);
  }
}

function bindSettingsForm() {
  if (!form) {
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    setStatusMessage("Сохраняю настройки...");

    try {
      await saveCurrentConfig();
      await Promise.all([loadLogs(), loadScript(), loadVpnStatus(), loadAutostartStatus()]);
    } catch (error) {
      setStatusMessage(error.message);
    }
  });
}

function bindResourceEditor() {
  if (!resourceEditor) {
    return;
  }

  resourceEditor.addEventListener("input", () => {
    syncSidebarResourcesFromEditor();
  });

  resourceEditor.addEventListener("click", (event) => {
    if (!event.target.classList.contains("remove-resource")) {
      return;
    }

    const rows = [...resourceEditor.querySelectorAll(".resource-row")];
    if (rows.length === 1) {
      renderResourceEditor([normalizeResource({}, 0)]);
    } else {
      event.target.closest(".resource-row").remove();
    }
    syncSidebarResourcesFromEditor();
  });

  bindClick("add-resource", () => {
    const resources = getResourcesFromEditor();
    resources.push(normalizeResource({}, resources.length));
    renderResourceEditor(resources);
    syncSidebarResourcesFromEditor();
  });
}

function bindActions() {
  bindClick("run-check", async () => {
    try {
      await runAction("/api/actions/check", "Проверка завершена.");
    } catch (error) {
      setStatusMessage(error.message);
    }
  });

  bindClick("run-rotate", async () => {
    try {
      await runAction("/api/actions/rotate", "Переключение завершено.");
    } catch (error) {
      setStatusMessage(error.message);
    }
  });

  bindClick("generate-script", async () => {
    try {
      await runAction("/api/actions/generate-script", "Скрипт пересобран.");
      if (!actionOutput && scriptOutput) {
        setConsole(scriptOutput, scriptOutput.textContent);
      }
    } catch (error) {
      setStatusMessage(error.message);
    }
  });

  bindClick("update-project", async () => {
    try {
      await runProjectUpdateFlow(setStatusMessage);
    } catch (error) {
      setStatusMessage(error.message);
    }
  });

  bindClick("reload-config", async () => {
    try {
      await loadConfig();
      setStatusMessage("Конфиг перечитан из файла.");
    } catch (error) {
      setStatusMessage(error.message);
    }
  });

  bindClick("refresh-state", async () => {
    try {
      await Promise.all([loadState(), loadVpnStatus()]);
      setStatusMessage("Состояние обновлено.");
    } catch (error) {
      setStatusMessage(error.message);
    }
  });

  bindClick("refresh-logs", async () => {
    try {
      await loadLogs();
      setStatusMessage("Логи обновлены.");
    } catch (error) {
      setStatusMessage(error.message);
    }
  });

  bindClick("clear-logs", async () => {
    try {
      setStatusMessage("Очищаю логи...");
      const result = await fetchJson("/api/actions/clear-logs", { method: "POST" });
      await Promise.all([loadLogs(), loadState()]);
      setStatusMessage(`Логи очищены.\n\n${JSON.stringify(result, null, 2)}`);
    } catch (error) {
      setStatusMessage(error.message);
    }
  });

  bindClick("refresh-script", async () => {
    try {
      await loadScript();
      setStatusMessage("Скрипт обновлён.");
    } catch (error) {
      setStatusMessage(error.message);
    }
  });

  bindClick("vpn-refresh-status", async () => {
    try {
      const status = await loadVpnStatus();
      setVpnMessage(formatVpnStatusText(status));
    } catch (error) {
      setVpnMessage(error.message);
    }
  });

  bindClick("vpn-refresh-locations", async () => {
    try {
      const locations = await loadVpnLocations();
      setVpnMessage(formatVpnLocationsText(locations));
    } catch (error) {
      setVpnMessage(error.message);
    }
  });

  bindClick("vpn-quick-connect", async () => {
    try {
      await runVpnAction(
        "/api/adguardvpn/connect",
        {},
        "Quick connect выполнен.",
        "Quick connect завершился с ошибкой."
      );
    } catch (error) {
      setVpnMessage(error.message);
    }
  });

  bindClick("vpn-connect-selected", async () => {
    try {
      const location = vpnLocationSelect?.value?.trim();
      await runVpnAction(
        "/api/adguardvpn/connect",
        location ? { location } : {},
        location ? `Подключение к ${location} выполнено.` : "Quick connect выполнен.",
        location ? `Подключение к ${location} завершилось с ошибкой.` : "Quick connect завершился с ошибкой."
      );
    } catch (error) {
      setVpnMessage(error.message);
    }
  });

  bindClick("vpn-disconnect", async () => {
    try {
      await runVpnAction(
        "/api/adguardvpn/disconnect",
        {},
        "Отключение выполнено.",
        "Отключение завершилось с ошибкой."
      );
    } catch (error) {
      setVpnMessage(error.message);
    }
  });

  bindClick("autostart-refresh-status", async () => {
    try {
      await loadAutostartStatus();
    } catch (error) {
      setAutostartMessage(error.message);
    }
  });

  bindClick("automation-refresh-status", async () => {
    try {
      await loadState();
      setStatusMessage("Статус автоматического режима обновлён.");
    } catch (error) {
      setStatusMessage(error.message);
    }
  });

  bindClick("automation-toggle", async () => {
    try {
      setStatusMessage("Обновляю автоматический режим...");
      const result = await toggleAutomationMode();
      setStatusMessage(
        `${result.message}\n\n${JSON.stringify(result.automation, null, 2)}`
      );
    } catch (error) {
      setStatusMessage(error.message);
    }
  });

  bindClick("autostart-apply", async () => {
    try {
      await saveCurrentConfig(false);
      const enabled = form?.elements?.namedItem("autostart.enabled")?.checked;
      await runAutostartAction(
        "/api/autostart/apply",
        { start_now: Boolean(enabled) },
        "Автозапуск применён."
      );
    } catch (error) {
      setAutostartMessage(error.message);
    }
  });

  bindClick("autostart-remove", async () => {
    try {
      await saveCurrentConfig(false);
      await runAutostartAction(
        "/api/autostart/remove",
        { stop_now: true },
        "Автозапуск удалён."
      );
    } catch (error) {
      setAutostartMessage(error.message);
    }
  });

  bindClick("project-update", async () => {
    try {
      await runProjectUpdateFlow(setAutostartMessage);
    } catch (error) {
      setAutostartMessage(error.message);
    }
  });
}

async function boot() {
  highlightActiveNav();
  bindSettingsForm();
  bindResourceEditor();
  bindActions();

  try {
    await Promise.all([
      loadConfig(),
      loadState(),
      loadLogs(),
      loadScript(),
      loadVpnStatus(),
      loadVpnLocations(),
      loadAutostartStatus(),
    ]);
    if (actionOutput) {
      setStatusMessage("Панель готова к работе.");
    }
    if (vpnOutput && !vpnOutput.textContent.trim()) {
      const status = await loadVpnStatus();
      setVpnMessage(formatVpnStatusText(status));
    }
    if (autostartOutput && !autostartOutput.textContent.trim()) {
      setAutostartMessage("Панель управления автозапуском готова.");
    }
  } catch (error) {
    setStatusMessage(error.message);
    if (logsOutput && !logsOutput.textContent.trim()) {
      setConsole(logsOutput, error.message);
    }
    if (scriptOutput && !scriptOutput.textContent.trim()) {
      setConsole(scriptOutput, error.message);
    }
    if (vpnOutput && !vpnOutput.textContent.trim()) {
      setVpnMessage(error.message);
    }
    if (autostartOutput && !autostartOutput.textContent.trim()) {
      setAutostartMessage(error.message);
    }
  }
}

boot();
