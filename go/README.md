# Keenetic VPN Panel — Go version

Это изолированная Go-реализация backend-а. Конфигурация и runtime-артефакты
хранятся внутри `go/`. Структурные HTML-страницы и значок разделяются между
реализациями через `../web` и `../assets`, а тема Go-панели находится в `go/web`.

Требования для сборки: Go 1.22 или новее. Внешних Go-зависимостей нет.

```sh
cd go
go test ./...
go build -trimpath -ldflags="-s -w" -o keenetic-vpn-panel .
./keenetic-vpn-panel
```

## Установка и миграция на Keenetic

Стабильная установка из GitHub Release:

```sh
curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/go/install/install.sh | sh
```

Установщик автоматически различает:

- обновление существующей Go-версии;
- Python-версию в `/opt/share/keenetic-vpn-panel/python`;
- старую установку Python непосредственно в `/opt/share/keenetic-vpn-panel`;
- чистую установку.

При миграции старый сервис сначала останавливается, `config.json` объединяется
с defaults Go-версии, а пути автозапуска заменяются на новые. Исходный JSON
сохраняется в `/opt/share/keenetic-vpn-panel/migration-backups`. Python-файлы
удаляются только после запуска новой службы и успешного HTTP health-check. При
ошибке установщик автоматически возвращает предыдущий каталог и init-скрипт.

Для обновления уже установленной версии:

```sh
/opt/share/keenetic-vpn-panel/go/install/update.sh
```

Удаление с сохранением конфигурации в каталоге резервных копий:

```sh
/opt/share/keenetic-vpn-panel/go/install/uninstall.sh
```

Установщик скачивает бинарник для архитектуры роутера и проверяет соседний
файл SHA-256. Для локальной проверки без GitHub Release можно передать
`LOCAL_BINARY=/path/to/keenetic-vpn-panel`.

Команды без HTTP-сервера:

```sh
./keenetic-vpn-panel rotate
./keenetic-vpn-panel sync-transparent-proxy
./keenetic-vpn-panel stop-transparent-proxy
```

Для роутера бинарник собирается на рабочей машине. Например, для Linux MIPSLE:

```sh
GOOS=linux GOARCH=mipsle GOMIPS=softfloat go build -trimpath -ldflags="-s -w" -o keenetic-vpn-panel .
```

Архитектуру конкретного роутера следует проверить через `uname -m`. После
проверки функционального паритета бинарник можно разместить в корне проекта;
Go-версия сама генерирует wrapper и autostart-файлы, которые запускают бинарник.

## AdGuard VPN CLI

Бинарник AdGuard VPN CLI не хранится в Git-репозитории: продукт не является
open source. Файл `adguardvpn-cli-manifest.json` закрепляет стабильную версию,
официальные архивы и SHA-256 для amd64, arm64, armv7, mips и mipsel.

Установка проверенного архива без пакетного менеджера:

```sh
sh install/install-adguardvpn-cli.sh
```

В панели кнопка «Проверить обновления» сравнивает текущую сборку панели с
веткой `master`, а установленный `adguardvpn-cli` — с последним стабильным
релизом AdGuardVPNCLI.

## Режимы маршрутизации

`transparent-redsocks` создаёт конфигурацию и управляет отдельным процессом
`redsocks`. TCP перенаправляется через NAT REDIRECT, обычный UDP — через
`redudp`, TPROXY и отдельную policy route table. DNS-запросы UDP направляются
во второй `redudp` к настроенному upstream DNS через SOCKS5 listener AdGuard
VPN CLI. DNS/TCP не перехватывается и остаётся на локальном резолвере. Для UDP
нужны пакет `redsocks`, команда `ip`, SOCKS5 с UDP и поддержка TPROXY ядром;
если TPROXY недоступен, используйте `tun-policy`.

`tun-policy` создаёт отдельные mangle/nat-цепочки, policy route table и `ip rule`
для TCP/UDP выбранных клиентов. Исключения применяются до маркировки. Если
заданы destination IP или домены, трафик фильтруется через два ipset; доменные
записи заполняет dnsmasq, поэтому его конфигурационный путь и команда
перезапуска должны соответствовать прошивке роутера. Диагностика доступна через
`GET /api/transparent-proxy/diagnostics`.

`nfqueue` запускает отдельный экземпляр `nfqws` и направляет в очередь только
заданные TCP/UDP-порты выбранных LAN-подсетей. Панель создаёт четыре собственных
списка: IP и домены для обработки, а также IP и доменные исключения. Внешние
файлы nfqws не изменяются. IP, домены, TCP и UDP оформляются независимыми
профилями nfqws (`--new`), поэтому include-списки работают как логическое ИЛИ,
а исключения применяются к каждому профилю. `GET /api/nfqueue/status` ищет стандартные списки
nfqws/nfqws2 и пути из их конфигураций, затем сообщает о точных и вложенных
совпадениях и конфликтах include/exclude. При обнаружении стороннего сервиса
применение блокируется, пока пользователь явно не разрешит параллельную работу.

Аппаратный flow offloading может обходить netfilter/NFQUEUE. Если правила есть,
но счётчики не растут, отключите offloading для диагностического теста.
