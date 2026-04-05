# Keenetic VPN Panel

Лёгкая веб-панель для управления shell-скриптом проверки ресурса и переключения локаций AdGuard VPN на Keenetic.

## Что уже есть

- Редактирование параметров проверки через браузер
- Генерация актуального shell-скрипта из `config.json`
- Ручная HTTP-проверка ресурса прямо из панели
- Запуск полного shell-сценария переключения
- Прямое управление `adguardvpn-cli` через web-интерфейс
- Отдельные страницы для обзора, параметров, логов и shell-скрипта
- Хранение быстрых ссылок на локальные web-ресурсы внутри бокового меню
- Просмотр статуса, логов и сгенерированного скрипта

## Структура

- `sctipt_test_location.txt` — исходный текущий shell-скрипт
- `config.json` — настройки панели и логики проверки
- `templates/adguardvpn_rotate.sh.tpl` — шаблон генерируемого скрипта
- `generated/adguardvpn-rotate.sh` — итоговый shell-скрипт после генерации
- `vpn_panel_server.py` — backend и HTTP API
- `web/` — интерфейс панели

## Запуск

```powershell
python vpn_panel_server.py
```

После запуска панель будет доступна по адресу:

```text
http://127.0.0.1:8088
```

## Важное замечание

Кнопка `Проверить ресурс` работает локально через Python.

Кнопка `Запустить переключение` запускает shell-скрипт через `panel.script_runner` из `config.json`. Для полноценной работы рядом должны быть:

- Unix-совместимая оболочка `sh`
- `curl`
- `adguardvpn-cli`
- доступ к файловым путям `/opt/...`

То есть полный сценарий рассчитан на Linux/Entware/роутерное окружение или совместимую среду вроде WSL с корректно настроенными путями и утилитами.

## Настройка

Если нужно поменять путь запуска shell-скрипта, откройте `config.json` и измените:

```json
"script_runner": "sh"
```

Например, в совместимой среде это может быть другая команда запуска оболочки.

## Запуск на Keenetic Ultra в локальной сети

Подход для самого роутера такой:

1. Установить Entware на накопитель или встроенную память роутера.
2. Установить в Entware `python3`, `ca-certificates` и сам `adguardvpn-cli`.
3. Скопировать этот проект на роутер, например в `/opt/share/keenetic-vpn-panel`.
4. В `config.json` для роутера указать:

```json
"host": "0.0.0.0"
```

Это позволит открывать панель из локальной сети по адресу вида `http://192.168.1.1:8088`.

5. Запустить панель вручную:

```sh
cd /opt/share/keenetic-vpn-panel
/opt/bin/python3 vpn_panel_server.py
```

6. Для автозапуска использовать шаблоны:

- `deploy/entware/start_vpn_panel.sh`
- `deploy/entware/S99keenetic-vpn-panel`

Обычно init-скрипт кладут в:

```sh
/opt/etc/init.d/S99keenetic-vpn-panel
```

После этого можно использовать:

```sh
/opt/etc/init.d/S99keenetic-vpn-panel start
/opt/etc/init.d/S99keenetic-vpn-panel status
```

## Что важно учесть на роутере

- Для доступа только из домашней сети не нужно публиковать этот порт наружу и не нужно делать проброс порта с WAN.
- Если хотите ограничить доступ жёстче, вместо `0.0.0.0` можно указать LAN-адрес самого роутера, например `192.168.1.1`.
- На слабых моделях роутеров лучше не держать тяжёлые фоновые процессы, но для этого проекта Python standard library обычно достаточно лёгкая.
- Вся shell-логика с путями `/opt/...` уже хорошо совпадает с окружением Entware.

## Установка с GitHub на роутере

После публикации репозитория по адресу:

```text
https://github.com/Phaum/keenetic-vpn-panel
```

установка одной командой будет выглядеть так:

```sh
/bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/main/install/install.sh)"
```

Если на роутере нет `curl`, можно использовать:

```sh
/bin/sh -c "$(wget -O- https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/main/install/install.sh)"
```

Что делает установщик:

- обновляет `opkg`
- устанавливает `python3`, `ca-certificates` и downloader при необходимости
- скачивает проект из GitHub
- размещает его в `/opt/share/keenetic-vpn-panel`
- настраивает `config.json` для LAN-доступа с `host = 0.0.0.0`
- устанавливает автозапуск через `/opt/etc/init.d/S99keenetic-vpn-panel`
- запускает сервис

После установки панель будет доступна по LAN-адресу роутера на порту `8088`.

## Обновление и удаление

Обновление:

```sh
/bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/main/install/update.sh)"
```

Удаление:

```sh
/bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/main/install/uninstall.sh)"
```

## Автозапуск из веб-панели

На странице настроек теперь есть отдельный блок автозапуска для Entware:

- путь к проекту
- путь к Python
- путь к лог-файлу
- путь к `init.d`-скрипту
- кнопки `Статус`, `Применить`, `Удалить`

То есть после установки через GitHub автозапуск можно дальше менять прямо из web-интерфейса, без ручного редактирования файлов на роутере.
