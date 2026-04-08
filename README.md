# Keenetic VPN Panel

Веб-панель для Keenetic и Entware, которая помогает проверять доступность нужного сайта, переключать локации AdGuard VPN и управлять этим через браузер без ручного редактирования shell-скриптов.

Проект рассчитан в первую очередь на запуск на роутере Keenetic с Entware, но его можно запускать и локально для настройки, отладки и разработки.

## Что умеет

- проверять доступность сайта по URL и ожидаемому тексту
- вручную запускать ротацию локаций AdGuard VPN
- автоматически проверять ресурс по расписанию и запускать ротацию при недоступности
- напрямую управлять `adguardvpn-cli` из веб-интерфейса
- показывать текущую локацию, последние действия и состояние панели
- хранить основной лог и отдельный debug-лог
- генерировать совместимый shell-wrapper для cron, init.d и ручного запуска
- обновляться с GitHub прямо из панели
- автоматически перезапускать веб-панель после успешного обновления

## Как это работает

Логика проекта разделена на две части:

- Python backend в [vpn_panel_server.py](/c:/files/keenetic/vpn/vpn_panel_server.py) выполняет проверки, ротацию, работу с `adguardvpn-cli`, автопроверку, обновление и API
- веб-интерфейс в папке [web](/c:/files/keenetic/vpn/web) показывает состояние и даёт кнопки для управления

Дополнительно проект генерирует shell-wrapper [generated/adguardvpn-rotate.sh](/c:/files/keenetic/vpn/generated/adguardvpn-rotate.sh), который можно использовать в старых сценариях, cron или init.d.

## Структура проекта

- [config.json](/c:/files/keenetic/vpn/config.json) — основной конфиг панели
- [vpn_panel_server.py](/c:/files/keenetic/vpn/vpn_panel_server.py) — backend и HTTP API
- [web/index.html](/c:/files/keenetic/vpn/web/index.html) — обзор и основные действия
- [web/settings.html](/c:/files/keenetic/vpn/web/settings.html) — настройки
- [web/logs.html](/c:/files/keenetic/vpn/web/logs.html) — просмотр логов
- [web/script.html](/c:/files/keenetic/vpn/web/script.html) — просмотр shell-wrapper
- [templates/adguardvpn_rotate.sh.tpl](/c:/files/keenetic/vpn/templates/adguardvpn_rotate.sh.tpl) — шаблон wrapper-скрипта
- [deploy/entware/start_vpn_panel.sh](/c:/files/keenetic/vpn/deploy/entware/start_vpn_panel.sh) — старт панели для Entware
- [deploy/entware/S99keenetic-vpn-panel](/c:/files/keenetic/vpn/deploy/entware/S99keenetic-vpn-panel) — init.d-скрипт
- [install/install.sh](/c:/files/keenetic/vpn/install/install.sh) — установка с GitHub
- [install/update.sh](/c:/files/keenetic/vpn/install/update.sh) — обновление
- [install/uninstall.sh](/c:/files/keenetic/vpn/install/uninstall.sh) — удаление

## Требования

Для полноценной работы на роутере нужны:

- `python3`
- `adguardvpn-cli`
- `ca-certificates`
- файловая структура Entware с путями `/opt/...`

Для локального запуска достаточно Python 3, но функции, завязанные на `adguardvpn-cli` и пути `/opt/...`, без роутерного окружения работать не будут или будут полезны только для интерфейсной отладки.

## Быстрый старт локально

Запуск из каталога проекта:

```powershell
python vpn_panel_server.py
```

По умолчанию панель открывается по адресу:

```text
http://127.0.0.1:8088
```

Локальный запуск удобен для:

- редактирования настроек
- разработки интерфейса
- проверки логики backend
- генерации wrapper-скрипта

## Быстрый старт на Keenetic

Если Entware уже установлен, самый простой вариант — установка одной командой:

```sh
/bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/install/install.sh)"
```

Если на роутере нет `curl`:

```sh
/bin/sh -c "$(wget -O- https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/install/install.sh)"
```

Установщик:

- обновляет `opkg`
- ставит зависимости
- скачивает проект в `/opt/share/keenetic-vpn-panel`
- настраивает `config.json`
- пытается найти свободный порт
- устанавливает автозапуск панели
- запускает сервис

После установки может понадобиться вход в аккаунт AdGuard VPN:

```sh
HOME=/opt/home/admin adguardvpn-cli login
```

## Ручной запуск на роутере

Если не используете установщик, можно поднять панель вручную:

```sh
cd /opt/share/keenetic-vpn-panel
/opt/bin/python3 vpn_panel_server.py
```

Чтобы панель была доступна из локальной сети, в [config.json](/c:/files/keenetic/vpn/config.json) обычно указывают:

```json
"panel": {
  "host": "0.0.0.0",
  "port": 8088
}
```

После этого панель будет доступна по адресу вида `http://192.168.1.1:8088`.

## Основные страницы интерфейса

### Обзор

Страница обзора показывает:

- результат последней проверки
- результат последней ротации
- состояние автоматического режима
- текущую локацию VPN
- кнопки ручной проверки и обновления

### Параметры

На странице настроек можно:

- менять URL и ожидаемый текст для проверки
- включать и выключать автоматический режим
- задавать интервал автопроверки
- настраивать `adguardvpn-cli`
- применять и удалять автозапуск панели как сервиса
- включать debug-лог

### Логи

Показываются:

- основной лог ротации
- debug-лог, если он включён

### Авто исполнитель

На этой странице можно посмотреть сгенерированный shell-wrapper, который остаётся совместимым с shell-сценариями и ручным запуском.

## Основные сценарии использования

### 1. Проверить ресурс вручную

Нажмите `Проверить ресурс`.

Панель выполнит HTTP-проверку через Python и покажет результат в интерфейсе.

### 2. Переключить локацию вручную

Нажмите `Запустить переключение`.

Панель:

- проверит ресурс
- если доступ есть, ничего переключать не будет
- если доступа нет, начнёт ротацию локаций
- сначала попробует последнюю удачную локацию
- затем переберёт доступные локации
- в конце попробует `quick connect`, если обычный перебор не помог

### 3. Включить автоматический режим

В настройках включите:

- `automation.enabled`
- задайте `automation.check_interval`

После этого запущенная панель будет сама выполнять проверки через заданный интервал.
Если ресурс недоступен, она автоматически запустит ротацию.

## Ключевые разделы конфига

### `panel`

Параметры самой веб-панели:

- `host`
- `port`
- `generated_script`

### `vpn`

Настройки проверки ресурса и логики ротации:

- `test_url`
- `expected_text`
- `timeout`
- `check_retries`
- `check_retry_delay`
- `switch_delay`
- `top_count`

### `adguardvpn`

Настройки CLI:

- `cli_command`
- `command_timeout`
- `locations_limit`

### `automation`

Настройки фоновой автопроверки:

```json
"automation": {
  "enabled": false,
  "check_interval": 600
}
```

- `enabled` — включает фоновую автопроверку
- `check_interval` — интервал между проверками в секундах

### `autostart`

Настройки запуска панели как сервиса Entware:

- `enabled`
- `service_name`
- `app_dir`
- `python_bin`
- `log_file`
- `pid_file`
- `start_script_path`
- `init_script_path`

Важно:

- `autostart` отвечает за запуск самой панели после перезагрузки
- `automation` отвечает за фоновые проверки внутри уже работающей панели

### `logging`

Настройки debug-лога:

```json
"logging": {
  "debug_enabled": false,
  "debug_log_file": "/opt/var/log/adguardvpn-rotate.debug.log",
  "debug_max_bytes": 262144,
  "debug_backup_count": 2
}
```

Если `debug_enabled = true`, панель пишет подробную трассировку:

- старт и завершение ротации
- HTTP-проверки по попыткам
- вызовы `adguardvpn-cli`
- работу lock-файла
- выбор локаций и fallback-сценарии

## Логи

По умолчанию используются такие файлы:

- основной лог: `/opt/var/log/adguardvpn-rotate.log`
- debug-лог: `/opt/var/log/adguardvpn-rotate.debug.log`
- лог самой панели: `/opt/var/log/keenetic-vpn-panel.log`

Если что-то работает не так, обычно стоит смотреть в таком порядке:

1. лог панели
2. основной лог ротации
3. debug-лог

Пример команды:

```sh
tail -n 60 /opt/var/log/keenetic-vpn-panel.log
```

## Обновление

Обновить проект можно двумя способами.

Через веб-интерфейс:

- кнопка `Обновить с GitHub`

Через консоль:

```sh
/bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/install/update.sh)"
```

После успешного обновления панель автоматически перезапускается.

Во время обновления скрипт старается:

- сохранить текущий `config.json`
- наложить пользовательские настройки поверх нового дефолтного конфига
- восстановить рабочий JSON даже если файл был частично повреждён

## Удаление

```sh
/bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/install/uninstall.sh)"
```

## Автозапуск панели как сервиса

Если панель установлена на роутере, она может запускаться через init.d.

Используются файлы:

- [deploy/entware/start_vpn_panel.sh](/c:/files/keenetic/vpn/deploy/entware/start_vpn_panel.sh)
- [deploy/entware/S99keenetic-vpn-panel](/c:/files/keenetic/vpn/deploy/entware/S99keenetic-vpn-panel)

Типовые команды:

```sh
/opt/etc/init.d/S99keenetic-vpn-panel start
/opt/etc/init.d/S99keenetic-vpn-panel stop
/opt/etc/init.d/S99keenetic-vpn-panel restart
/opt/etc/init.d/S99keenetic-vpn-panel status
```

Этими же настройками можно управлять из веб-панели на странице параметров.

## Что важно учитывать

- Не публикуйте панель в интернет без дополнительной защиты.
- Для домашнего использования обычно достаточно LAN-доступа.
- Если не нужен доступ со всех интерфейсов, вместо `0.0.0.0` лучше указать конкретный LAN IP роутера.
- На слабых моделях роутеров лучше не ставить слишком частую автопроверку.
- Проверка зависит не только от доступности сайта, но и от совпадения `expected_text`.

## Типичные проблемы

### Панель открывается, но VPN-переключение не работает

Проверьте:

- установлен ли `adguardvpn-cli`
- выполнен ли вход через `adguardvpn-cli login`
- доступны ли пути `/opt/...`

### Автоматический режим включён, но ничего не происходит

Проверьте:

- что сама панель запущена
- что `automation.enabled = true`
- что интервал не слишком большой
- что в логах нет ошибок HTTP-проверки или вызова CLI

### Debug-лог не появляется

Проверьте:

- что `logging.debug_enabled = true`
- что процесс панели может писать в каталог `/opt/var/log`

### После обновления панель не поднялась

Смотрите лог панели:

```sh
tail -n 60 /opt/var/log/keenetic-vpn-panel.log
```

Также имеет смысл проверить, существует ли init.d-скрипт и корректны ли пути в секции `autostart`.

## Репозиторий

GitHub проекта:

```text
https://github.com/Phaum/keenetic-vpn-panel
```
