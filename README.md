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
- `generated/adguardvpn-rotate.sh` — shell-wrapper для запуска Python-ротации
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

Кнопка `Запустить переключение` запускает Python-native ротацию прямо из `vpn_panel_server.py`.

Сгенерированный файл `generated/adguardvpn-rotate.sh` остаётся как совместимый shell-wrapper для cron, init.d и ручного запуска на роутере.

Для полноценной работы рядом должны быть:

- Unix-совместимая оболочка `sh` для wrapper-скрипта
- `python3`
- `adguardvpn-cli`
- доступ к файловым путям `/opt/...`

То есть полный сценарий рассчитан на Linux/Entware/роутерное окружение или совместимую среду вроде WSL с корректно настроенными путями и утилитами.

## Детальное логирование

В `config.json` есть секция `logging`:

```json
"logging": {
  "debug_enabled": false,
  "debug_log_file": "/opt/var/log/adguardvpn-rotate.debug.log",
  "debug_max_bytes": 262144,
  "debug_backup_count": 2
}
```

Если `debug_enabled = true`, панель начинает писать подробную трассировку:

- старт и завершение ротации
- lock-файл и пропуски параллельных запусков
- каждый вызов `adguardvpn-cli`
- HTTP-проверки ресурса по попыткам
- выбор локаций, fallback и quick connect

Основной лог остаётся коротким, а debug-лог используется для диагностики.

## Настройка

Если нужно поменять путь интерпретатора для wrapper-скрипта, откройте `config.json` и измените:

```json
"python_bin": "/opt/bin/python3"
```

Это поле находится в секции `autostart`. Параметр `panel.script_runner` оставлен для совместимости, но основная ротация теперь выполняется в Python.

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

установка одной командой будет выглядеть так:

```sh
/bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/install/install.sh)"
```

Если на роутере нет `curl`, можно использовать:

```sh
/bin/sh -c "$(wget -O- https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/install/install.sh)"
```

Что делает установщик:

- обновляет `opkg`
- устанавливает `python3`, `ca-certificates`, `curl`, `sudo` и downloader при необходимости
- автоматически ставит `adguardvpn-cli` по инструкции для Keenetic и создаёт симлинк `/opt/bin/adguardvpn-cli`
- скачивает проект из GitHub
- размещает его в `/opt/share/keenetic-vpn-panel`
- настраивает `config.json` для LAN-доступа с `host = 0.0.0.0`
- автоматически выбирает свободный порт, если стандартный конфликтует с сервисами Keenetic
- пытается определить LAN IP роутера и выводит готовый URL, например `http://192.168.1.1:18091`
- устанавливает автозапуск через `/opt/etc/init.d/S99keenetic-vpn-panel`
- запускает сервис

После установки `adguardvpn-cli` может потребоваться отдельный вход в аккаунт:

```sh
HOME=/opt/home/admin adguardvpn-cli login
```

После установки панель будет доступна по LAN-адресу роутера на выбранном установщиком порту.

## Обновление и удаление

Обновление:

```sh
/bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/install/update.sh)"
```

То же обновление можно запускать из веб-панели кнопкой `Обновить с GitHub`.

Во время обновления установщик сохраняет существующий `config.json`, накладывает его поверх нового дефолтного конфига из репозитория и старается восстановить первый валидный JSON-объект даже если файл был повреждён.

Если после обновления сервис не поднялся, первым делом посмотрите лог:

```sh
tail -n 60 /opt/var/log/keenetic-vpn-panel.log
```

Удаление:

```sh
/bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/master/install/uninstall.sh)"
```

## Автозапуск из веб-панели

На странице настроек теперь есть отдельный блок автозапуска для Entware:

- путь к проекту
- путь к Python
- путь к лог-файлу
- путь к `init.d`-скрипту
- кнопки `Статус`, `Применить`, `Удалить`

То есть после установки через GitHub автозапуск можно дальше менять прямо из web-интерфейса, без ручного редактирования файлов на роутере.
