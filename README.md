# Keenetic VPN Panel

Веб-панель для управления AdGuard VPN CLI на Keenetic с Entware. Актуальная
версия написана на Go, не требует Python во время работы и объединяет управление
VPN, автоматическую смену локаций, проверку доступности ресурсов и настройку
маршрутизации LAN-клиентов.

По умолчанию панель слушает только `127.0.0.1:8088`. Не публикуйте её напрямую
в интернет: API выполняет административные действия и рассчитан на доверенное
локальное окружение.

## Возможности

- первичная настройка через web wizard;
- проверка наличия и состояния AdGuard VPN CLI;
- вход в аккаунт и установка CLI из панели;
- подключение, отключение и выбор VPN-локации;
- ручная и автоматическая ротация локаций при недоступности ресурса;
- тёмная и светлая темы, сворачиваемое боковое меню;
- контроль обновлений панели и AdGuard VPN CLI;
- автозапуск через Entware init script;
- четыре режима маршрутизации: `router-only`, `transparent-redsocks`,
  `tun-policy` и `nfqueue`;
- миграция конфигурации со старой Python-версии с резервной копией и откатом.

## Архитектура

```text
.
├── go/                         Go backend и runtime-конфигурация
│   ├── main.go                 HTTP API, VPN-команды и автоматизация
│   ├── config.go               defaults, валидация и миграция config.json
│   ├── system.go               runtime-артефакты и управление сервисами
│   ├── redsocks_mode.go        TCP, UDP/TPROXY и DNS через redsocks
│   ├── network_modes.go        TUN policy routing
│   ├── nfqueue.go              NFQUEUE/nfqws
│   ├── setup.go                мастер первого запуска и установка CLI
│   ├── updates.go              проверка обновлений
│   ├── web/                    Go-тема и JavaScript setup wizard
│   └── install/                install, update, uninstall и CLI installer
├── web/                        общие HTML-страницы и логика интерфейса
├── assets/                     favicon и общие ресурсы
├── python/                     legacy-реализация для истории и миграции
└── .github/workflows/          сборка release-бинарников
```

Go-сервер загружает конфигурацию из `go/config.json`, создаёт runtime-файлы в
`go/generated/` и обслуживает общие страницы из `web/`. При установке на роутер
корень приложения — `/opt/share/keenetic-vpn-panel`, а исполняемый файл и
конфигурация находятся в `/opt/share/keenetic-vpn-panel/go`.

Python-версия больше не является основной и находится в [`python/`](python/).
Новая установка должна использовать Go-версию.

## Быстрый локальный запуск

Требуется Go 1.22 или новее. Внешних Go-модулей у проекта нет.

```sh
git clone --branch go-version --single-branch https://github.com/Phaum/keenetic-vpn-panel.git
cd keenetic-vpn-panel/go
go test ./...
go build -trimpath -ldflags="-s -w" -o keenetic-vpn-panel .
./keenetic-vpn-panel
```

Откройте:

```text
http://127.0.0.1:8088
```

Для запуска без предварительной сборки:

```sh
cd go
go run .
```

Интерфейс и безопасные read-only проверки работают на обычном Linux. Операции
с `iptables`, `ip`, `ipset`, TPROXY и системными маршрутами требуют Linux,
соответствующих модулей ядра и прав администратора.

## Конфигурация первого запуска

При отсутствии конфигурации Go-версия создаёт `go/config.json` и открывает
мастер настройки. В нём можно:

1. выбрать режим маршрутизации;
2. указать LAN-подсети клиентов;
3. настроить URL и ожидаемый текст для проверки доступности;
4. включить периодическую автоматическую проверку;
5. проверить установку AdGuard VPN CLI и войти в аккаунт.

Расширенные параметры доступны на странице «Параметры». Изменения сетевого
режима применяйте только при локальном доступе к роутеру: ошибочная подсеть,
маршрут или firewall rule могут прервать соединение.

## Установка на Keenetic / Entware

Требуется установленный Entware с доступными `/opt` и `opkg`.

```sh
curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/go-version/go/install/install.sh | sh
```

Если `curl` отсутствует:

```sh
wget -qO- https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/go-version/go/install/install.sh | sh
```

Установщик:

- определяет архитектуру `amd64`, `arm64`, `armv7`, `mips` или `mipsle`;
- устанавливает доступные Entware-пакеты `ca-certificates`, `ip-full`, `ipset`
  и `redsocks`;
- скачивает release-бинарник и проверяет его SHA-256;
- сохраняет предыдущую конфигурацию;
- мигрирует существующую Go- или Python-установку;
- создаёт `/opt/etc/init.d/S99keenetic-vpn-panel`;
- запускает сервис и выполняет HTTP health check;
- автоматически откатывает установку, если новая версия не запустилась.

После установки панель доступна на настроенном адресе, по умолчанию:

```text
http://127.0.0.1:8088
```

Для доступа с компьютера используйте безопасный SSH port forwarding либо явно
измените `panel.host`, понимая, что встроенной пользовательской авторизации пока
нет.

## AdGuard VPN CLI

AdGuard VPN CLI не хранится в репозитории. Манифест
[`go/adguardvpn-cli-manifest.json`](go/adguardvpn-cli-manifest.json) закрепляет
поддерживаемую стабильную версию, официальные URL архивов и SHA-256.

CLI можно установить кнопкой быстрой установки в панели или вручную:

```sh
cd /opt/share/keenetic-vpn-panel/go
sh install/install-adguardvpn-cli.sh
```

После установки выполните вход через мастер настройки или командой:

```sh
HOME=/opt/home/admin adguardvpn-cli login
```

## Режимы маршрутизации

### `router-only`

Панель управляет AdGuard VPN CLI, но не меняет маршруты и firewall. Подходит,
если маршрутизация уже настроена на роутере другим способом.

### `transparent-redsocks`

TCP перенаправляется через NAT REDIRECT и `redsocks`. Обычный UDP проходит
через `redudp`, TPROXY и отдельную policy routing table. DNS/UDP направляется
через отдельный `redudp` к настроенному upstream DNS через SOCKS5 listener
AdGuard VPN CLI. DNS/TCP остаётся на локальном резолвере.

Для UDP нужны команда `ip`, SOCKS5 с поддержкой UDP и TPROXY в ядре роутера.
Если прошивка не поддерживает TPROXY, используйте `tun-policy`.

### `tun-policy`

Полноценная маршрутизация TCP и UDP выбранных LAN-клиентов через TUN-интерфейс.
Панель создаёт `ip rule`, отдельную routing table и правила маркировки. Можно
ограничить обработку destination CIDR или доменами через `dnsmasq + ipset`.

### `nfqueue`

Панель запускает собственный экземпляр `nfqws` и направляет в него выбранные
TCP/UDP-порты. Собственные include/exclude-списки не изменяют файлы уже
установленного nfqws. Параллельная работа блокируется до явного разрешения,
если найден сторонний сервис.

Аппаратный flow offloading может обходить netfilter и NFQUEUE. Если правила
установлены, но их счётчики не растут, временно отключите offloading для
диагностики.

## Управление сервисом

```sh
/opt/etc/init.d/S99keenetic-vpn-panel status
/opt/etc/init.d/S99keenetic-vpn-panel restart
/opt/etc/init.d/S99keenetic-vpn-panel stop
```

Backend также поддерживает команды без запуска HTTP-сервера:

```sh
cd /opt/share/keenetic-vpn-panel/go
./keenetic-vpn-panel rotate
./keenetic-vpn-panel sync-transparent-proxy
./keenetic-vpn-panel stop-transparent-proxy
```

## Обновление и удаление

Обновление установленной версии:

```sh
/opt/share/keenetic-vpn-panel/go/install/update.sh
```

Удаление с сохранением резервной копии конфигурации:

```sh
/opt/share/keenetic-vpn-panel/go/install/uninstall.sh
```

Проверка обновлений также доступна из web-панели. Release workflow собирает
статические Linux-бинарники для всех поддерживаемых архитектур и публикует
рядом SHA-256-файлы.

## Разработка и проверка

```sh
cd go
go fmt ./...
go test -race ./...
go vet ./...
go build -trimpath -ldflags="-s -w" .
node --check ../web/app.js
node --check web/ui.js
```

Синтаксис установочных скриптов:

```sh
for script in go/install/*.sh; do sh -n "$script"; done
```

Для сборки под MIPSLE:

```sh
cd go
CGO_ENABLED=0 GOOS=linux GOARCH=mipsle GOMIPS=softfloat \
  go build -trimpath -ldflags="-s -w" -o keenetic-vpn-panel-linux-mipsle .
```

## Ограничения безопасности

- web API пока не имеет встроенной аутентификации;
- оставляйте `panel.host=127.0.0.1` или закрывайте доступ reverse proxy/SSH;
- не публикуйте порт панели напрямую в WAN;
- сетевые режимы изменяют `iptables`, routing tables и процессы роутера;
- перед обновлением или изменением маршрутизации сохраняйте рабочую
  конфигурацию и обеспечьте резервный локальный доступ к устройству.

Дополнительные технические детали находятся в [`go/README.md`](go/README.md).
