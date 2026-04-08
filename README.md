# Keenetic VPN Panel

Веб-панель для роутеров с Entware и локального Linux-окружения, которая управляет `adguardvpn-cli`, проверяет доступность ресурсов, переключает локации и умеет работать как автономный transport layer без ручной настройки маршрутов в веб-панели Keenetic.

Проект изначально ориентирован на Keenetic, но последние версии логики маршрутизации сделаны так, чтобы их можно было использовать и на других роутерах, где доступны `adguardvpn-cli`, `iptables`, `ipset`, `dnsmasq` и `ip`.

## Что умеет

- проверять доступность сайта по URL и ожидаемому тексту
- вручную запускать ротацию локаций AdGuard VPN
- автоматически проверять ресурс по расписанию и запускать ротацию при недоступности
- напрямую управлять `adguardvpn-cli` из веб-интерфейса
- работать в трёх transport-режимах:
  - `router-only`
  - `transparent-redsocks`
  - `tun-policy`
- делать selective routing по:
  - destination IP/CIDR
  - доменам через `dnsmasq -> ipset -> iptables`
- автоматически генерировать служебные shell-скрипты и runtime-конфиги
- показывать состояние VPN, transport layer, автопроверки и последних действий
- хранить основной лог и отдельный debug-лог
- обновляться с GitHub прямо из панели
- автоматически перезапускать сервис панели после успешного обновления

## Режимы работы

### `router-only`

Панель управляет только `adguardvpn-cli`.

Маршрутизация остаётся внешней:

- либо через веб-панель роутера
- либо через сторонние скрипты
- либо через уже существующую сетевую конфигурацию

Это режим совместимости со старой схемой.

### `transparent-redsocks`

TCP-only режим.

Панель:

- переводит `adguardvpn-cli` в SOCKS mode
- поднимает `redsocks`
- вешает `iptables` NAT redirect
- при необходимости ограничивает редирект только на выбранные destination CIDR и домены

Подходит, если нужен прозрачный TCP-прокси поверх listener-а `adguardvpn-cli`.

Ограничение:

- UDP как транспорт через этот режим не проходит

### `tun-policy`

Основной автономный режим в актуальной версии проекта.

Панель:

- переводит `adguardvpn-cli` в `TUN` mode
- ставит `set-tun-routing-mode NONE`
- определяет TUN-интерфейс автоматически или использует явно заданный
- создаёт policy routing через `ip rule` и `ip route`
- маркирует трафик через `iptables mangle`
- умеет selective routing по destination CIDR и доменам
- может перехватывать DNS клиентов на локальный `dnsmasq`

Это режим для полноценного TCP+UDP transport слоя без участия веб-панели роутера.

## Как устроен проект

Основная логика находится в [vpn_panel_server.py](/c:/files/keenetic/vpn/vpn_panel_server.py).

Этот backend:

- поднимает HTTP API
- выполняет HTTP-проверки ресурса
- запускает ротацию локаций
- вызывает `adguardvpn-cli`
- готовит transport mode
- генерирует runtime-артефакты:
  - `redsocks.conf`
  - shell-скрипты apply/remove
  - `dnsmasq` fragment для `ipset`
- синхронизирует сетевой слой при:
  - `connect`
  - `disconnect`
  - `rotate`
  - сохранении конфига
  - старте сервиса

Веб-часть находится в папке [web](/c:/files/keenetic/vpn/web):

- [web/index.html](/c:/files/keenetic/vpn/web/index.html)
- [web/settings.html](/c:/files/keenetic/vpn/web/settings.html)
- [web/logs.html](/c:/files/keenetic/vpn/web/logs.html)
- [web/script.html](/c:/files/keenetic/vpn/web/script.html)
- [web/app.js](/c:/files/keenetic/vpn/web/app.js)

Панель также продолжает генерировать wrapper-скрипт [templates/adguardvpn_rotate.sh.tpl](/c:/files/keenetic/vpn/templates/adguardvpn_rotate.sh.tpl) для старых сценариев запуска.

## Что требуется на роутере

Для полноценной работы нужны:

- `python3`
- `adguardvpn-cli`
- `redsocks`
- `iptables`
- `ipset`
- `dnsmasq` с поддержкой `ipset`
- рабочая команда `ip`
- `ca-certificates`
- Entware-пути `/opt/...`

Для локального запуска на обычной машине достаточно Python 3, но:

- вызовы `adguardvpn-cli` без роутерного окружения не будут полноценно полезны
- сетевые transport-режимы тоже имеют смысл только на Linux/роутере

## Установка на Keenetic / Entware

Если Entware уже установлен, можно использовать установщик:

```sh
/bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/install/install.sh)"
```

Если `curl` нет:

```sh
/bin/sh -c "$(wget -O- https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/install/install.sh)"
```

Установщик:

- обновляет `opkg`
- ставит зависимости
- скачивает проект в `/opt/share/keenetic-vpn-panel`
- восстанавливает или нормализует `config.json`
- выбирает свободный порт панели
- настраивает автозапуск
- пытается включить zero-touch transport-конфигурацию для fresh install

При установке он также:

- ставит `redsocks`
- ставит `ipset`
- пытается поставить пакет с командой `ip`
- пытается определить путь для `dnsmasq` fragment
- пытается определить команду перезапуска `dnsmasq`
- для новой установки ориентируется на `tun-policy`

После установки почти наверняка потребуется логин в AdGuard VPN:

```sh
HOME=/opt/home/admin adguardvpn-cli login
```

### Что означает “из коробки”

В актуальной версии это значит:

- проект сам готовит transport-конфиг
- сам генерирует `dnsmasq` fragment
- сам переключает `adguardvpn-cli` transport mode
- сам поднимает и снимает сетевой слой при операциях VPN

Но всё ещё остаются аппаратно-зависимые места:

- автоматическое определение TUN-интерфейса
- конкретный init script `dnsmasq`
- наличие нужных модулей `iptables` и `ipset` в системе

Если роутер сильно отличается от типичного Entware-окружения, может потребоваться руками уточнить:

- `transparent_proxy.tun_interface`
- `transparent_proxy.dnsmasq_restart_command`
- `transparent_proxy.dnsmasq_ipset_config_path`

## Локальный запуск

Для отладки интерфейса и backend-логики:

```powershell
python vpn_panel_server.py
```

По умолчанию панель открывается на:

```text
http://127.0.0.1:8088
```

## Страницы панели

### Обзор

Показывает:

- последнюю проверку
- последнюю ротацию
- состояние автопроверки
- состояние VPN
- состояние transport layer

### Параметры

Позволяет:

- редактировать основной конфиг
- переключать transport mode
- задавать LAN-подсети клиентов
- задавать selective routing по CIDR и доменам
- управлять автозапуском
- включать debug-лог

### Логи

Показывает:

- основной лог ротации
- debug-лог

### Авто исполнитель

Показывает сгенерированный wrapper-скрипт для старых shell-сценариев.

## Selective routing

Проект умеет работать в двух вариантах:

### Full routing

Если `destination_subnets` и `destination_domains` пустые, то весь трафик клиентов из `target_subnets` уходит через выбранный transport mode.

### Selective routing

Если заполнен хотя бы один список:

- `transparent_proxy.destination_subnets`
- `transparent_proxy.destination_domains`

то в VPN уходит только трафик к этим назначениям.

### Маршрутизация по доменам

Для доменов используется цепочка:

`dnsmasq -> ipset -> iptables`

Это означает:

- панель генерирует `dnsmasq`-fragment с правилами `ipset`
- `dnsmasq` складывает IP-адреса доменов в `ipset`
- `iptables` применяет правила только к IP из этого `ipset`

Важно:

- это не “магическая” маршрутизация по строке домена в пакетах
- домен сначала должен быть реально разрешён через тот `dnsmasq`, который читает сгенерированный fragment

## DNS и UDP

### В `transparent-redsocks`

- TCP поддерживается
- UDP как transport не поддерживается
- домены можно использовать как селектор для TCP-правил

### В `tun-policy`

- TCP и UDP маршрутизируются через TUN
- может включаться DNS hijack для клиентов
- доменные selective-правила остаются через `dnsmasq/ipset`

Именно `tun-policy` является актуальным режимом для полноценной UDP/DNS-схемы.

## CLI-команды

Помимо запуска веб-панели, backend поддерживает:

```sh
/opt/bin/python3 vpn_panel_server.py rotate
/opt/bin/python3 vpn_panel_server.py sync-transparent-proxy
/opt/bin/python3 vpn_panel_server.py stop-transparent-proxy
```

## Автозапуск

На Entware используются:

- [deploy/entware/start_vpn_panel.sh](/c:/files/keenetic/vpn/deploy/entware/start_vpn_panel.sh)
- [deploy/entware/S99keenetic-vpn-panel](/c:/files/keenetic/vpn/deploy/entware/S99keenetic-vpn-panel)

Типовые команды:

```sh
/opt/etc/init.d/S99keenetic-vpn-panel start
/opt/etc/init.d/S99keenetic-vpn-panel stop
/opt/etc/init.d/S99keenetic-vpn-panel restart
/opt/etc/init.d/S99keenetic-vpn-panel status
```

## Обновление

Через веб-интерфейс:

- кнопка `Обновить с GitHub`

Через консоль:

```sh
/bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/install/update.sh)"
```

После успешного обновления панель автоматически перезапускается.

## Удаление

```sh
/bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/install/uninstall.sh)"
```

## Основные разделы `config.json`

### `panel`

Настройки самой панели:

- `host`
- `port`
- `script_runner`
- `source_script`
- `generated_script`

### `vpn`

Параметры проверки и ротации:

- `test_url`
- `expected_text`
- `top_count`
- `timeout`
- `connect_timeout`
- `check_retries`
- `check_retry_delay`
- `switch_delay`

### `adguardvpn`

Настройки CLI:

- `cli_command`
- `command_timeout`
- `locations_limit`

### `automation`

Фоновая проверка:

- `enabled`
- `check_interval`

### `transparent_proxy`

Главный блок transport layer.

Ключевые поля:

- `mode`
- `proxy_type`
- `proxy_host`
- `proxy_port`
- `listen_ip`
- `listen_port`
- `redsocks_bin`
- `redsocks_pid_file`
- `redsocks_config_path`
- `iptables_path`
- `ipset_path`
- `ip_path`
- `chain_name`
- `target_subnets`
- `bypass_subnets`
- `destination_subnets`
- `destination_domains`
- `destination_subnet_set`
- `destination_domain_set`
- `dnsmasq_ipset_config_path`
- `dnsmasq_restart_command`
- `tun_interface`
- `tun_route_table`
- `tun_fwmark`
- `tun_rule_priority`
- `dns_hijack_enabled`
- `dns_hijack_port`
- `rules_script_path`
- `stop_script_path`

Практический смысл:

- `target_subnets` — какие клиенты или LAN-сегменты вообще участвуют в проксировании
- `destination_subnets` — какие destination CIDR нужно отправлять в VPN
- `destination_domains` — какие домены нужно отправлять в VPN через `dnsmasq/ipset`
- `bypass_subnets` — какие сети нельзя трогать

### `autostart`

Параметры запуска панели как сервиса:

- `enabled`
- `service_name`
- `app_dir`
- `python_bin`
- `log_file`
- `pid_file`
- `start_script_path`
- `init_script_path`

### `paths`

Служебные runtime-файлы:

- `lock_file`
- `log_file`
- `good_file`
- `tmp_file`
- `body_file`

### `logging`

Debug-лог:

- `debug_enabled`
- `debug_log_file`
- `debug_max_bytes`
- `debug_backup_count`

### `resources`

Ссылки в боковом меню.

Это обычные `http/https` URL, поэтому можно указывать:

- доменные адреса
- IP-адреса

## Логи

По умолчанию используются:

- `/opt/var/log/adguardvpn-rotate.log`
- `/opt/var/log/adguardvpn-rotate.debug.log`
- `/opt/var/log/keenetic-vpn-panel.log`

Если что-то идёт не так, обычно полезно смотреть в таком порядке:

1. лог панели
2. основной лог ротации
3. debug-лог

Пример:

```sh
tail -n 60 /opt/var/log/keenetic-vpn-panel.log
```

## Ограничения и важные замечания

- `transparent-redsocks` — это TCP-only режим
- доменная маршрутизация зависит от реально используемого `dnsmasq`
- `dnsmasq_ipset_config_path` должен попадать в конфиг, который `dnsmasq` действительно читает
- для доменных правил после изменения конфигурации нужен реальный restart `dnsmasq`, а не просто абстрактный “reload”
- автоопределение TUN-интерфейса сделано эвристически
- если на роутере нет нужных netfilter-модулей, selective routing работать не будет
- панель не стоит публиковать в интернет без дополнительной защиты

## Типичные проблемы

### Панель открывается, но VPN-переключение не работает

Проверьте:

- установлен ли `adguardvpn-cli`
- выполнен ли `adguardvpn-cli login`
- доступны ли пути `/opt/...`

### `tun-policy` включён, но трафик не идёт через VPN

Проверьте:

- что `adguardvpn-cli` действительно в `TUN` mode
- что TUN-интерфейс найден автоматически или явно задан
- что доступны `ip`, `iptables`, `ipset`
- что policy routing не конфликтует с другой сетевой логикой роутера

### Доменные selective-правила не работают

Проверьте:

- что `destination_domains` заполнен корректно
- что `dnsmasq_ipset_config_path` лежит в реально загружаемом `conf-dir`
- что `dnsmasq_restart_command` корректен
- что клиенты действительно резолвят DNS через этот `dnsmasq`

### `transparent-redsocks` включён, но ничего не проксируется

Проверьте:

- что `adguardvpn-cli` подключён в SOCKS mode
- что есть listener в `adguardvpn-cli status`
- что `redsocks` установлен
- что `target_subnets` совпадает с реальными LAN-подсетями

### Debug-лог не появляется

Проверьте:

- что `logging.debug_enabled = true`
- что процесс панели может писать в `/opt/var/log`

## Репозиторий

GitHub проекта:

```text
https://github.com/Phaum/keenetic-vpn-panel
```
