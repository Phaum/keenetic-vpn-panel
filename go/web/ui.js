(() => {
  const icons = {
    dashboard: '<svg viewBox="0 0 24 24"><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"/></svg>',
    settings: '<svg viewBox="0 0 24 24"><path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z"/><path d="M4.9 7.1 3.7 5.9l2.2-2.2 1.2 1.2A8.7 8.7 0 0 1 10 3.7V2h4v1.7a8.7 8.7 0 0 1 2.9 1.2l1.2-1.2 2.2 2.2-1.2 1.2a8.7 8.7 0 0 1 1.2 2.9H22v4h-1.7a8.7 8.7 0 0 1-1.2 2.9l1.2 1.2-2.2 2.2-1.2-1.2a8.7 8.7 0 0 1-2.9 1.2V22h-4v-1.7a8.7 8.7 0 0 1-2.9-1.2l-1.2 1.2-2.2-2.2 1.2-1.2A8.7 8.7 0 0 1 3.7 14H2v-4h1.7a8.7 8.7 0 0 1 1.2-2.9Z"/></svg>',
    logs: '<svg viewBox="0 0 24 24"><path d="M5 3h14v18H5z"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
    script: '<svg viewBox="0 0 24 24"><path d="m9 7-5 5 5 5M15 7l5 5-5 5M13 4l-2 16"/></svg>',
    github: '<svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 0 0-3.2 19.5v-2.2c-2.7.6-3.3-1.1-3.3-1.1-.4-1.1-1.1-1.4-1.1-1.4-.9-.6.1-.6.1-.6 1 0 1.5 1 1.5 1 .9 1.5 2.3 1.1 2.9.8.1-.6.3-1.1.6-1.3-2.1-.2-4.4-1.1-4.4-4.7 0-1 .4-1.9 1-2.6-.1-.3-.4-1.3.1-2.6 0 0 .8-.3 2.7 1a9.4 9.4 0 0 1 4.9 0c1.9-1.3 2.7-1 2.7-1 .5 1.3.2 2.3.1 2.6.7.7 1 1.6 1 2.6 0 3.6-2.2 4.4-4.4 4.7.4.3.7.9.7 1.8v3A10 10 0 0 0 12 2Z"/></svg>',
  };

  const shell = document.querySelector('.app-shell');
  const sidebar = document.querySelector('.sidebar');
  if (!shell || !sidebar) return;

  sidebar.setAttribute('aria-label', 'Основная навигация');
  document.querySelectorAll('.nav-link').forEach((link) => {
    const key = link.dataset.nav || 'github';
    const label = link.textContent.trim();
    link.innerHTML = `<span class="nav-icon" aria-hidden="true">${icons[key] || icons.github}</span><span class="nav-text">${label}</span>`;
    link.title = label;
  });

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'sidebar-toggle';
  toggle.innerHTML = '<span class="toggle-icon" aria-hidden="true">☰</span><span class="toggle-label">Свернуть меню</span>';
  sidebar.append(toggle);

  const mobileToggle = document.createElement('button');
  mobileToggle.type = 'button';
  mobileToggle.className = 'mobile-menu-toggle';
  mobileToggle.setAttribute('aria-label', 'Открыть меню');
  mobileToggle.innerHTML = '<span></span><span></span><span></span>';
  document.querySelector('.workspace')?.prepend(mobileToggle);

  const backdrop = document.createElement('button');
  backdrop.type = 'button';
  backdrop.className = 'sidebar-backdrop';
  backdrop.setAttribute('aria-label', 'Закрыть меню');
  shell.append(backdrop);

  const applyCollapsed = (collapsed) => {
    shell.classList.toggle('menu-collapsed', collapsed);
    toggle.querySelector('.toggle-label').textContent = collapsed ? 'Развернуть меню' : 'Свернуть меню';
    toggle.setAttribute('aria-label', collapsed ? 'Развернуть меню' : 'Свернуть меню');
    localStorage.setItem('keenetic-go-menu-collapsed', String(collapsed));
  };

  applyCollapsed(localStorage.getItem('keenetic-go-menu-collapsed') === 'true');
  toggle.addEventListener('click', () => applyCollapsed(!shell.classList.contains('menu-collapsed')));
  mobileToggle.addEventListener('click', () => shell.classList.add('menu-open'));
  backdrop.addEventListener('click', () => shell.classList.remove('menu-open'));
  document.querySelectorAll('.nav-link').forEach((link) => link.addEventListener('click', () => shell.classList.remove('menu-open')));
})();

(() => {
  const root = document.documentElement;
  const storedTheme = localStorage.getItem('keenetic-go-theme');
  const queryTheme = new URLSearchParams(location.search).get('theme');
  const initialTheme = ['light', 'dark'].includes(queryTheme) ? queryTheme : (storedTheme || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
  root.dataset.theme = initialTheme;

  const actions = document.querySelector('.topbar .action-cluster');
  if (!actions) return;

  const setupButton = document.createElement('button');
  setupButton.type = 'button';
  setupButton.className = 'ghost setup-open-button';
  setupButton.textContent = 'Первый запуск';

  const updatesButton = document.createElement('button');
  updatesButton.type = 'button';
  updatesButton.className = 'ghost updates-check-button';
  updatesButton.textContent = 'Проверить обновления';

  const themeButton = document.createElement('button');
  themeButton.type = 'button';
  themeButton.className = 'ghost theme-toggle';
  const renderThemeButton = () => {
    themeButton.textContent = root.dataset.theme === 'light' ? 'Тёмная тема' : 'Светлая тема';
    themeButton.setAttribute('aria-label', themeButton.textContent);
  };
  renderThemeButton();
  themeButton.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'light' ? 'dark' : 'light';
    localStorage.setItem('keenetic-go-theme', root.dataset.theme);
    renderThemeButton();
  });
  actions.prepend(themeButton);
  actions.prepend(updatesButton);
  actions.prepend(setupButton);
  const legacyUpdateButton = document.querySelector('#update-project');
  if (legacyUpdateButton) legacyUpdateButton.hidden = true;

  const updatesDialog = document.createElement('dialog');
  updatesDialog.className = 'updates-dialog';
  updatesDialog.innerHTML = '<header><h2>Обновления</h2><button type="button" class="ghost updates-close">×</button></header><div class="updates-content">Проверяем версии…</div>';
  document.body.append(updatesDialog);
  updatesDialog.querySelector('.updates-close').addEventListener('click', () => updatesDialog.close());
  updatesButton.addEventListener('click', async () => {
    const content = updatesDialog.querySelector('.updates-content');
    content.textContent = 'Проверяем панель и AdGuard VPN CLI…';
    updatesDialog.showModal();
    try {
      const response = await fetch('/api/updates/check');
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      const panel = data.panel || {};
      const cli = data.adguardvpn_cli || {};
      const localCLI = cli.local?.version || (cli.local?.available ? 'не определена' : 'не установлен');
      content.innerHTML = `
        <article><span>Панель</span><strong>${panel.update_available ? 'Доступно обновление' : (panel.comparison_available ? 'Актуальная версия' : 'Версия сборки не определена')}</strong><small>Локально: ${panel.current_commit || panel.current_version || 'unknown'} · GitHub: ${panel.latest_commit || panel.error || 'недоступен'}</small></article>
        <article><span>AdGuard VPN CLI</span><strong>${cli.update_available ? 'Доступно обновление' : 'Актуальная версия'}</strong><small>Локально: ${localCLI} · Стабильная: ${cli.latest_version || cli.error || data.pinned_cli_version}</small></article>
        <article><span>Архитектура</span><strong>${data.architecture}</strong><small>${cli.supported_architecture ? 'Официальная сборка доступна.' : 'Официальной сборки для этой архитектуры нет.'}</small></article>`;
    } catch (error) { content.textContent = error.message; }
  });

  const overlay = document.createElement('div');
  overlay.className = 'setup-overlay';
  overlay.hidden = true;
  overlay.innerHTML = `
    <section class="setup-dialog" role="dialog" aria-modal="true" aria-labelledby="setup-title">
      <header class="setup-header">
        <div><p class="section-eyebrow">Go setup</p><h2 id="setup-title">Настройка VPN-панели</h2></div>
        <button type="button" class="setup-close ghost" aria-label="Закрыть">×</button>
      </header>
      <div class="setup-progress" aria-label="Этапы настройки">
        <button type="button" data-setup-step="0" class="active"><b>1</b><span>Режим</span></button>
        <button type="button" data-setup-step="1"><b>2</b><span>Аккаунт</span></button>
        <button type="button" data-setup-step="2"><b>3</b><span>Проверка</span></button>
      </div>
      <form id="setup-form">
        <div class="setup-step active" data-step-panel="0">
          <h3>Режим работы</h3>
          <p class="setup-copy">Выберите, какой трафик роутер будет направлять через AdGuard VPN.</p>
          <div class="mode-selector">
            <label><input type="radio" name="mode" value="router-only"><span><strong>Router only</strong><small>Только управление CLI, без изменения маршрутов.</small></span></label>
            <label><input type="radio" name="mode" value="transparent-redsocks"><span><strong>Transparent redsocks</strong><small>Прозрачные TCP, UDP/TPROXY и DNS через SOCKS5.</small></span></label>
            <label><input type="radio" name="mode" value="tun-policy"><span><strong>TUN policy</strong><small>TCP и UDP через policy routing. Рекомендуется для Keenetic.</small></span></label>
            <label><input type="radio" name="mode" value="nfqueue"><span><strong>NFQUEUE / nfqws</strong><small>Обработка выбранного трафика через nfqws со списками и исключениями.</small></span></label>
          </div>
          <div class="setup-fields">
            <label data-setup-modes="transparent-redsocks tun-policy nfqueue">Подсети клиентов<input name="target_subnets" required placeholder="192.168.1.0/24"></label>
            <label data-setup-modes="tun-policy">TUN-интерфейс<input name="tun_interface" placeholder="auto"></label>
            <label class="full-span" data-setup-modes="tun-policy">Маршрутизировать только подсети назначения<textarea name="destination_subnets" placeholder="Оставьте пустым для всего трафика"></textarea></label>
            <label class="full-span" data-setup-modes="tun-policy">Домены назначения<textarea name="destination_domains" placeholder="telegram.org, example.com"></textarea></label>
            <div class="hint-card full-span" data-setup-modes="nfqueue">IP, доменные списки, исключения и стратегии nfqws можно настроить после завершения мастера в разделе «Параметры».</div>
          </div>
        </div>
        <div class="setup-step" data-step-panel="1">
          <h3>Аккаунт AdGuard VPN</h3>
          <p class="setup-copy">Авторизация выполняется официальным browser-flow. Пароль не передаётся панели и не сохраняется.</p>
          <div class="installation-state" id="setup-installation-state">Проверяем установку AdGuard VPN CLI…</div>
          <div class="account-state" id="setup-account-state">Проверяем состояние CLI…</div>
          <div class="setup-inline-actions">
            <button type="button" class="primary" id="setup-install-cli">Быстро установить CLI</button>
            <button type="button" class="primary" id="setup-login-start">Войти в аккаунт</button>
            <button type="button" class="ghost" id="setup-login-check">Проверить вход</button>
          </div>
          <pre class="console setup-login-output" id="setup-login-output">Ожидание запуска авторизации.</pre>
          <div class="hint-card">Если CLI требует настоящий терминал, выполните по SSH:<br><code>HOME=/opt/home/admin adguardvpn-cli login</code>, затем нажмите «Проверить вход».</div>
        </div>
        <div class="setup-step" data-step-panel="2">
          <h3>Проверка и автоматизация</h3>
          <div class="setup-fields">
            <label class="full-span">URL проверки<input name="test_url" type="url" required></label>
            <label class="full-span">Ожидаемый текст<input name="expected_text" required></label>
            <label>Интервал проверки, сек<input name="check_interval" type="number" min="1" value="600"></label>
            <label class="setup-checkbox"><input name="automation_enabled" type="checkbox"><span>Включить автоматическую проверку</span></label>
          </div>
          <div class="setup-summary" id="setup-summary"></div>
        </div>
        <footer class="setup-footer">
          <button type="button" class="ghost" id="setup-back">Назад</button>
          <span id="setup-message"></span>
          <button type="button" class="primary" id="setup-next">Продолжить</button>
          <button type="submit" class="primary" id="setup-finish">Сохранить настройку</button>
        </footer>
      </form>
    </section>`;
  document.body.append(overlay);

  const form = overlay.querySelector('#setup-form');
  const message = overlay.querySelector('#setup-message');
  const loginOutput = overlay.querySelector('#setup-login-output');
  const accountState = overlay.querySelector('#setup-account-state');
  const installationState = overlay.querySelector('#setup-installation-state');
  let step = 0;
  let pollTimer;

  const api = async (url, options = {}) => {
    const response = await fetch(url, {headers: {'Content-Type': 'application/json'}, ...options});
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || body.message || `HTTP ${response.status}`);
    return body;
  };
  const showStep = (next) => {
    step = Math.max(0, Math.min(2, next));
    overlay.querySelectorAll('[data-step-panel]').forEach((panel) => panel.classList.toggle('active', Number(panel.dataset.stepPanel) === step));
    overlay.querySelectorAll('[data-setup-step]').forEach((button) => button.classList.toggle('active', Number(button.dataset.setupStep) <= step));
    overlay.querySelector('#setup-back').hidden = step === 0;
    overlay.querySelector('#setup-next').hidden = step === 2;
    overlay.querySelector('#setup-finish').hidden = step !== 2;
    if (step === 2) updateSummary();
  };
  const open = () => { overlay.hidden = false; document.body.classList.add('setup-open'); showStep(0); };
  const close = () => { overlay.hidden = true; document.body.classList.remove('setup-open'); clearTimeout(pollTimer); };
  const setValue = (name, value) => { const field = form.elements.namedItem(name); if (field && value != null) field.value = value; };
  const updateModeFields = () => {
    const mode = form.elements.namedItem('mode').value || 'router-only';
    overlay.querySelectorAll('[data-setup-modes]').forEach((element) => {
      const hidden = !element.dataset.setupModes.split(/\s+/).includes(mode);
      element.classList.toggle('mode-hidden', hidden);
      element.querySelectorAll('input, textarea, select').forEach((control) => { control.disabled = hidden; });
    });
  };
  const updateSummary = () => {
    const data = new FormData(form);
    overlay.querySelector('#setup-summary').innerHTML = `<strong>Будет сохранено</strong><span>Режим: ${data.get('mode')}</span><span>Клиенты: ${data.get('target_subnets')}</span><span>Проверка: ${data.get('test_url')}</span>`;
  };
  const renderAccount = (account) => {
    if (!account?.available) { accountState.className = 'account-state warning'; accountState.textContent = 'adguardvpn-cli не найден. Настройку можно сохранить и выполнить вход позже.'; return; }
    accountState.className = `account-state ${account.authenticated ? 'success' : 'warning'}`;
    accountState.textContent = account.authenticated ? 'Вход выполнен, лицензия доступна.' : 'CLI доступен, но вход в аккаунт не подтверждён.';
  };
  const renderInstallation = (installation) => {
    const installButton = overlay.querySelector('#setup-install-cli');
    if (!installation?.installed) {
      installationState.className = 'installation-state warning';
      installationState.innerHTML = `<strong>AdGuard VPN CLI не установлен</strong><span>${installation?.message || 'Исполняемый файл не найден.'}</span><code>${installation?.install_command || 'sh install/install-adguardvpn-cli.sh'}</code>`;
      overlay.querySelector('#setup-login-start').disabled = true;
      installButton.hidden = false;
      installButton.disabled = installation?.supported_architecture === false;
      installButton.textContent = installation?.supported_architecture === false ? 'Архитектура не поддерживается' : 'Быстро установить CLI';
      return;
    }
    installationState.className = `installation-state ${installation.runnable ? 'success' : 'warning'}`;
    installationState.innerHTML = `<strong>${installation.runnable ? 'AdGuard VPN CLI установлен' : 'CLI найден, но не запускается'}</strong><span>${installation.version || installation.executable}</span><small>${installation.executable}</small>`;
    overlay.querySelector('#setup-login-start').disabled = !installation.runnable;
    installButton.hidden = installation.runnable === true;
    installButton.disabled = false;
    installButton.textContent = 'Переустановить CLI';
  };
  const loadStatus = async (autoOpen = false) => {
    try {
      const config = await api('/api/config');
      if (autoOpen) {
        if (config.setup?.completed === true) { close(); return; }
        open();
      }
      setValue('target_subnets', config.transparent_proxy?.target_subnets || '192.168.1.0/24');
      setValue('tun_interface', config.transparent_proxy?.tun_interface || 'auto');
      setValue('destination_subnets', config.transparent_proxy?.destination_subnets || '');
      setValue('destination_domains', config.transparent_proxy?.destination_domains || '');
      setValue('test_url', config.vpn?.test_url || 'https://example.com/');
      setValue('expected_text', config.vpn?.expected_text || 'Example Domain');
      setValue('check_interval', config.automation?.check_interval || 600);
      form.elements.namedItem('automation_enabled').checked = Boolean(config.automation?.enabled);
      const status = await api('/api/setup/status');
      const mode = form.querySelector(`[name="mode"][value="${status.mode || 'router-only'}"]`);
      if (mode) mode.checked = true;
      updateModeFields();
      renderInstallation(status.installation);
      renderAccount(status.account);
    } catch (error) { message.textContent = error.message; }
  };
  const pollLogin = async () => {
    const status = await api('/api/adguardvpn/login/status');
    loginOutput.textContent = status.output || status.error || 'Ожидание подтверждения в браузере…';
    if (status.running) pollTimer = setTimeout(pollLogin, 1200);
    else await loadStatus(false);
  };

  setupButton.addEventListener('click', () => { open(); loadStatus(false); });
  overlay.querySelector('.setup-close').addEventListener('click', close);
  overlay.querySelector('#setup-back').addEventListener('click', () => showStep(step - 1));
  overlay.querySelector('#setup-next').addEventListener('click', () => {
    if (step === 0 && !form.elements.namedItem('mode').value) { message.textContent = 'Выберите режим работы.'; return; }
    message.textContent = ''; showStep(step + 1);
  });
  overlay.querySelectorAll('[data-setup-step]').forEach((button) => button.addEventListener('click', () => showStep(Number(button.dataset.setupStep))));
  overlay.querySelectorAll('[name="mode"]').forEach((input) => input.addEventListener('change', updateModeFields));
  overlay.querySelector('#setup-login-start').addEventListener('click', async () => { loginOutput.textContent = 'Запуск авторизации…'; const status = await api('/api/adguardvpn/login/start', {method:'POST', body:'{}'}); loginOutput.textContent = status.output || status.error || 'Ожидание browser-flow…'; if (status.running) pollLogin(); });
  overlay.querySelector('#setup-install-cli').addEventListener('click', async () => {
    const button = overlay.querySelector('#setup-install-cli');
    button.disabled = true;
    button.textContent = 'Установка…';
    installationState.className = 'installation-state';
    installationState.innerHTML = '<strong>Устанавливаем AdGuard VPN CLI</strong><span>Загрузка и проверка SHA-256 могут занять несколько минут.</span>';
    loginOutput.textContent = 'Запуск проверенного установщика…';
    try {
      const result = await api('/api/adguardvpn/install', {method:'POST', body:'{}'});
      loginOutput.textContent = [result.message, result.stdout, result.stderr].filter(Boolean).join('\n\n');
      renderInstallation(result.status);
      if (result.status?.runnable) await loadStatus(false);
    } catch (error) {
      loginOutput.textContent = `Ошибка установки: ${error.message}`;
      button.disabled = false;
      button.textContent = 'Повторить установку';
      await loadStatus(false);
    }
  });
  overlay.querySelector('#setup-login-check').addEventListener('click', () => loadStatus(false));
  form.addEventListener('submit', async (event) => {
    event.preventDefault(); message.textContent = 'Сохраняем…';
    const data = new FormData(form);
    const payload = Object.fromEntries(data.entries());
    payload.automation_enabled = form.elements.namedItem('automation_enabled').checked;
    payload.check_interval = Number(payload.check_interval);
    try { await api('/api/setup/complete', {method:'POST', body:JSON.stringify(payload)}); message.textContent = 'Настройка завершена.'; setTimeout(() => location.reload(), 500); }
    catch (error) { message.textContent = error.message; }
  });
  showStep(0);
  open();
  loadStatus(true);
})();
