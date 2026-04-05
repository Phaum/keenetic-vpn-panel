from __future__ import annotations

import json
import re
import shlex
import shutil
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
TEMPLATE_PATH = BASE_DIR / "templates" / "adguardvpn_rotate.sh.tpl"
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "panel": {
        "host": "127.0.0.1",
        "port": 8088,
        "script_runner": "sh",
        "source_script": "sctipt_test_location.txt",
        "generated_script": "generated/adguardvpn-rotate.sh",
    },
    "vpn": {
        "test_url": "https://example.com/",
        "expected_text": "Example Domain",
        "top_count": 10,
        "timeout": 15,
        "connect_timeout": 8,
        "check_retries": 3,
        "check_retry_delay": 5,
        "switch_delay": 10,
    },
    "adguardvpn": {
        "cli_command": "adguardvpn-cli",
        "command_timeout": 30,
        "locations_limit": 20,
    },
    "autostart": {
        "enabled": False,
        "service_name": "keenetic-vpn-panel",
        "app_dir": "/opt/share/keenetic-vpn-panel",
        "python_bin": "/opt/bin/python3",
        "log_file": "/opt/var/log/keenetic-vpn-panel.log",
        "pid_file": "/opt/var/run/keenetic-vpn-panel.pid",
        "start_script_path": "/opt/share/keenetic-vpn-panel/deploy/entware/start_vpn_panel.sh",
        "init_script_path": "/opt/etc/init.d/S99keenetic-vpn-panel",
    },
    "paths": {
        "lock_file": "/opt/tmp/adguardvpn-switch.lock",
        "log_file": "/opt/var/log/adguardvpn-rotate.log",
        "good_file": "/opt/tmp/adguardvpn-good-location.txt",
        "tmp_file": "/opt/tmp/adguardvpn-locations.txt",
        "body_file": "/opt/tmp/adguardvpn-check-body.txt",
    },
    "resources": {
        "links": [
            {
                "name": "Keenetic Router",
                "url": "http://192.168.1.1",
                "description": "Router UI",
                "group": "Router",
            },
            {
                "name": "Home Assistant",
                "url": "http://192.168.1.20:8123",
                "description": "Automation",
                "group": "Smart Home",
            },
        ]
    },
}

SHELL_IMPORT_MAP = {
    "TEST_URL": ("vpn", "test_url"),
    "EXPECTED_TEXT": ("vpn", "expected_text"),
    "TOP_COUNT": ("vpn", "top_count"),
    "TIMEOUT": ("vpn", "timeout"),
    "CONNECT_TIMEOUT": ("vpn", "connect_timeout"),
    "CHECK_RETRIES": ("vpn", "check_retries"),
    "CHECK_RETRY_DELAY": ("vpn", "check_retry_delay"),
    "SWITCH_DELAY": ("vpn", "switch_delay"),
    "LOCK_FILE": ("paths", "lock_file"),
    "LOG_FILE": ("paths", "log_file"),
    "GOOD_FILE": ("paths", "good_file"),
    "TMP_FILE": ("paths", "tmp_file"),
    "BODY_FILE": ("paths", "body_file"),
}

STATE_LOCK = threading.Lock()
ACTION_LOCK = threading.Lock()
STATE: dict[str, Any] = {
    "last_check": None,
    "last_rotation": None,
    "last_script_generation": None,
    "last_cli_action": None,
    "last_vpn_status": None,
    "last_vpn_locations": None,
    "last_autostart_action": None,
}

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def deep_copy(data: Any) -> Any:
    return json.loads(json.dumps(data))


def merge_defaults(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deep_copy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_defaults(result[key], value)
        else:
            result[key] = value
    return result


def import_from_shell_script(path: Path) -> dict[str, Any]:
    imported = deep_copy(DEFAULT_CONFIG)
    if not path.exists():
        return imported

    content = path.read_text(encoding="utf-8")
    for variable, target in SHELL_IMPORT_MAP.items():
        match = re.search(
            rf"^{re.escape(variable)}=(?:\"([^\"]*)\"|'([^']*)'|([^\n#]+))",
            content,
            flags=re.MULTILINE,
        )
        if not match:
            continue

        raw = next(group for group in match.groups() if group is not None).strip()
        section, key = target
        imported[section][key] = int(raw) if raw.isdigit() else raw

    return imported


def write_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_config() -> dict[str, Any]:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return merge_defaults(DEFAULT_CONFIG, raw)


def ensure_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        return load_config()

    source = BASE_DIR / DEFAULT_CONFIG["panel"]["source_script"]
    config = import_from_shell_script(source)
    write_config(config)
    return config


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = merge_defaults(DEFAULT_CONFIG, config)

    required_strings = [
        ("panel", "host"),
        ("panel", "script_runner"),
        ("panel", "source_script"),
        ("panel", "generated_script"),
        ("adguardvpn", "cli_command"),
        ("autostart", "service_name"),
        ("autostart", "app_dir"),
        ("autostart", "python_bin"),
        ("autostart", "log_file"),
        ("autostart", "pid_file"),
        ("autostart", "start_script_path"),
        ("autostart", "init_script_path"),
        ("vpn", "test_url"),
        ("vpn", "expected_text"),
        ("paths", "lock_file"),
        ("paths", "log_file"),
        ("paths", "good_file"),
        ("paths", "tmp_file"),
        ("paths", "body_file"),
    ]

    for section, key in required_strings:
        value = str(merged[section].get(key, "")).strip()
        if not value:
            raise ValueError(f"Field '{section}.{key}' must not be empty")
        merged[section][key] = value

    positive_int_fields = [
        ("panel", "port"),
        ("adguardvpn", "command_timeout"),
        ("adguardvpn", "locations_limit"),
        ("vpn", "top_count"),
        ("vpn", "timeout"),
        ("vpn", "connect_timeout"),
        ("vpn", "check_retries"),
        ("vpn", "check_retry_delay"),
        ("vpn", "switch_delay"),
    ]

    for section, key in positive_int_fields:
        try:
            value = int(merged[section][key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Field '{section}.{key}' must be an integer") from exc
        if value <= 0:
            raise ValueError(f"Field '{section}.{key}' must be greater than zero")
        merged[section][key] = value

    merged["autostart"]["enabled"] = bool(merged.get("autostart", {}).get("enabled", False))

    resources = merged.get("resources", {})
    links = resources.get("links", [])
    if not isinstance(links, list):
        raise ValueError("Field 'resources.links' must be an array")

    normalized_links: list[dict[str, str]] = []
    for index, item in enumerate(links, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Resource #{index} must be an object")

        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        description = str(item.get("description", "")).strip()
        group = str(item.get("group", "")).strip()

        if not name:
            raise ValueError(f"Resource #{index} must contain a name")
        if not url:
            raise ValueError(f"Resource #{index} must contain a url")

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Resource #{index} url must be a valid http/https address")

        normalized_links.append(
            {
                "name": name,
                "url": url,
                "description": description,
                "group": group or "LAN",
            }
        )

    merged["resources"] = {"links": normalized_links}

    return merged


def resolve_local_path(relative_or_absolute: str) -> Path:
    path = Path(relative_or_absolute)
    return path if path.is_absolute() else (BASE_DIR / path).resolve()


def render_script(config: dict[str, Any]) -> str:
    vpn = config["vpn"]
    paths = config["paths"]
    content = TEMPLATE_PATH.read_text(encoding="utf-8")
    replacements = {
        "test_url": shlex.quote(vpn["test_url"]),
        "expected_text": shlex.quote(vpn["expected_text"]),
        "top_count": vpn["top_count"],
        "timeout": vpn["timeout"],
        "connect_timeout": vpn["connect_timeout"],
        "check_retries": vpn["check_retries"],
        "check_retry_delay": vpn["check_retry_delay"],
        "switch_delay": vpn["switch_delay"],
        "lock_file": shlex.quote(paths["lock_file"]),
        "log_file": shlex.quote(paths["log_file"]),
        "good_file": shlex.quote(paths["good_file"]),
        "tmp_file": shlex.quote(paths["tmp_file"]),
        "body_file": shlex.quote(paths["body_file"]),
    }

    for key, value in replacements.items():
        content = content.replace(f"${{{key}}}", str(value))

    return content


def generate_script(config: dict[str, Any]) -> dict[str, Any]:
    script_path = resolve_local_path(config["panel"]["generated_script"])
    script_path.parent.mkdir(parents=True, exist_ok=True)
    content = render_script(config)
    script_path.write_text(content, encoding="utf-8", newline="\n")

    try:
        script_path.chmod(script_path.stat().st_mode | 0o111)
    except OSError:
        pass

    payload = {
        "script_path": str(script_path),
        "generated_at": utc_now(),
        "size": script_path.stat().st_size,
    }

    with STATE_LOCK:
        STATE["last_script_generation"] = payload

    return payload


def tail_file(path: Path, lines: int = 200) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(reversed(content[-lines:]))


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def read_last_good_location(config: dict[str, Any]) -> str | None:
    good_path = Path(config["paths"]["good_file"])
    if not good_path.exists():
        return None
    text = strip_ansi(good_path.read_text(encoding="utf-8", errors="replace")).strip()
    return text or None


def write_last_good_location(config: dict[str, Any], location: str | None) -> None:
    if not location:
        return
    good_path = Path(config["paths"]["good_file"])
    try:
        good_path.parent.mkdir(parents=True, exist_ok=True)
        good_path.write_text(strip_ansi(location).strip() + "\n", encoding="utf-8")
    except OSError:
        return


def perform_http_check(config: dict[str, Any]) -> dict[str, Any]:
    vpn = config["vpn"]
    attempts: list[dict[str, Any]] = []
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    for attempt_index in range(1, vpn["check_retries"] + 1):
        started_at = time.time()
        attempt_result: dict[str, Any] = {
            "attempt": attempt_index,
            "started_at": utc_now(),
            "success": False,
        }
        try:
            request = urllib.request.Request(
                vpn["test_url"],
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(
                request,
                timeout=vpn["timeout"],
                context=context,
            ) as response:
                body = response.read().decode("utf-8", errors="replace")
                status_code = response.getcode()
                contains_text = vpn["expected_text"] in body
                attempt_result.update(
                    {
                        "status_code": status_code,
                        "contains_expected_text": contains_text,
                        "duration_ms": round((time.time() - started_at) * 1000, 2),
                    }
                )
                if status_code in (200, 301, 302) and contains_text:
                    attempt_result["success"] = True
                    attempts.append(attempt_result)
                    result = {
                        "success": True,
                        "message": "Ресурс доступен и ожидаемый текст найден.",
                        "attempts": attempts,
                        "checked_at": utc_now(),
                    }
                    with STATE_LOCK:
                        STATE["last_check"] = result
                    return result

                attempt_result["message"] = "Ответ получен, но проверка текста не пройдена."
        except urllib.error.HTTPError as exc:
            attempt_result.update(
                {
                    "status_code": exc.code,
                    "message": f"HTTP error: {exc.code}",
                    "duration_ms": round((time.time() - started_at) * 1000, 2),
                }
            )
        except Exception as exc:  # noqa: BLE001
            attempt_result.update(
                {
                    "message": str(exc),
                    "duration_ms": round((time.time() - started_at) * 1000, 2),
                }
            )

        attempts.append(attempt_result)
        if attempt_index < vpn["check_retries"]:
            time.sleep(vpn["check_retry_delay"])

    result = {
        "success": False,
        "message": "Ресурс недоступен или страница не содержит ожидаемый текст.",
        "attempts": attempts,
        "checked_at": utc_now(),
    }
    with STATE_LOCK:
        STATE["last_check"] = result
    return result


def run_rotation(config: dict[str, Any]) -> dict[str, Any]:
    with ACTION_LOCK:
        generation = generate_script(config)
        script_path = Path(generation["script_path"])
        runner = shlex.split(config["panel"]["script_runner"])
        if not runner:
            raise ValueError("Field 'panel.script_runner' must not be empty")

        if shutil.which(runner[0]) is None:
            result = {
                "success": False,
                "message": f"Команда запуска '{runner[0]}' не найдена в PATH.",
                "executed_at": utc_now(),
                "stdout": "",
                "stderr": "",
                "returncode": None,
                "command": runner + [str(script_path)],
            }
            with STATE_LOCK:
                STATE["last_rotation"] = result
            return result

        command = runner + [str(script_path)]
        timeout = max(config["vpn"]["timeout"], 30) + config["vpn"]["switch_delay"] * 3
        try:
            completed = subprocess.run(
                command,
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            result = {
                "success": completed.returncode == 0,
                "message": "Скрипт отработал успешно." if completed.returncode == 0 else "Скрипт завершился с ошибкой.",
                "executed_at": utc_now(),
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "returncode": completed.returncode,
                "command": command,
            }
        except subprocess.TimeoutExpired as exc:
            result = {
                "success": False,
                "message": "Запуск скрипта превысил таймаут.",
                "executed_at": utc_now(),
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "returncode": None,
                "command": command,
            }

        with STATE_LOCK:
            STATE["last_rotation"] = result
        return result


def command_exists(command: str) -> bool:
    if shutil.which(command):
        return True
    return Path(command).exists()


def run_adguardvpn_cli(
    config: dict[str, Any],
    args: list[str],
    *,
    timeout: int | None = None,
) -> dict[str, Any]:
    cli_parts = shlex.split(config["adguardvpn"]["cli_command"])
    if not cli_parts:
        return {
            "success": False,
            "available": False,
            "message": "Команда adguardvpn-cli не настроена.",
            "executed_at": utc_now(),
            "stdout": "",
            "stderr": "",
            "returncode": None,
            "command": [],
        }

    if not command_exists(cli_parts[0]):
        return {
            "success": False,
            "available": False,
            "message": f"Команда '{cli_parts[0]}' не найдена в PATH.",
            "executed_at": utc_now(),
            "stdout": "",
            "stderr": "",
            "returncode": None,
            "command": cli_parts + args,
        }

    command = cli_parts + args
    try:
        completed = subprocess.run(
            command,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout or config["adguardvpn"]["command_timeout"],
            check=False,
        )
        return {
            "success": completed.returncode == 0,
            "available": True,
            "message": "Команда выполнена." if completed.returncode == 0 else "Команда завершилась с ошибкой.",
            "executed_at": utc_now(),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
            "command": command,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "success": False,
            "available": True,
            "message": "Команда adguardvpn-cli превысила таймаут.",
            "executed_at": utc_now(),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "returncode": None,
            "command": command,
        }


def parse_adguardvpn_status(result: dict[str, Any]) -> dict[str, Any]:
    status = {
        "available": result.get("available", False),
        "success": result.get("success", False),
        "message": result.get("message", ""),
        "executed_at": result.get("executed_at"),
        "connected": False,
        "location": None,
        "account": None,
        "device": None,
        "mode": None,
        "listener": None,
        "raw": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "returncode": result.get("returncode"),
        "command": result.get("command", []),
    }

    if not result.get("success"):
        return status

    text = result.get("stdout", "").replace("\r", "")
    clean_text = strip_ansi(text)
    parsed: dict[str, str] = {}
    for line in clean_text.splitlines():
        if not re.match(r"^[A-Za-z][A-Za-z0-9 _-]*:\s*", line):
            continue
        key, value = line.split(":", 1)
        parsed[key.strip().lower()] = value.strip()

    mode = None
    listener = None
    location = parsed.get("location") or parsed.get("current location")
    first_line = clean_text.splitlines()[0].strip() if clean_text.splitlines() else ""
    connected_match = re.search(
        r"Connected to\s+(.+?)\s+in\s+(.+?)\s+mode,\s+listening on\s+(.+)$",
        first_line,
        flags=re.IGNORECASE,
    )
    if connected_match:
        location = connected_match.group(1).strip()
        mode = connected_match.group(2).strip()
        listener = connected_match.group(3).strip()

    account = parsed.get("account")
    device = parsed.get("device")
    state_value = (
        parsed.get("state")
        or parsed.get("status")
        or parsed.get("connection status")
        or ""
    ).lower()
    connected = bool(location) or "connected" in clean_text.lower()
    if state_value:
        connected = connected or "connected" in state_value

    status.update(
        {
            "connected": connected,
            "location": location,
            "account": account,
            "device": device,
            "mode": mode,
            "listener": listener,
            "parsed": parsed,
            "clean_raw": clean_text,
        }
    )
    return status


def parse_adguardvpn_locations(result: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "available": result.get("available", False),
        "success": result.get("success", False),
        "message": result.get("message", ""),
        "executed_at": result.get("executed_at"),
        "items": [],
        "raw": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "returncode": result.get("returncode"),
        "command": result.get("command", []),
    }

    if not result.get("success"):
        return payload

    lines = strip_ansi(result.get("stdout", "").replace("\r", "")).splitlines()
    header_found = False
    items: list[dict[str, str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^ISO\s+COUNTRY", stripped, flags=re.IGNORECASE):
            header_found = True
            continue
        if stripped.lower().startswith("you can connect"):
            break
        if not header_found:
            continue

        columns = re.split(r"\s{2,}", stripped)
        if len(columns) < 4:
            continue

        code, country, city, score = columns[:4]
        items.append(
            {
                "code": code,
                "country": country,
                "city": city,
                "score": score,
                "raw": stripped,
            }
        )

    payload["items"] = items
    payload["message"] = f"Найдено локаций: {len(items)}" if items else payload["message"]
    payload["clean_raw"] = "\n".join(lines)
    return payload


def get_adguardvpn_status(config: dict[str, Any]) -> dict[str, Any]:
    result = parse_adguardvpn_status(run_adguardvpn_cli(config, ["status"]))
    if result.get("connected") and result.get("location"):
        write_last_good_location(config, result["location"])
    with STATE_LOCK:
        STATE["last_vpn_status"] = result
    return result


def get_adguardvpn_locations(config: dict[str, Any], limit: int | None = None) -> dict[str, Any]:
    safe_limit = limit or config["adguardvpn"]["locations_limit"]
    result = parse_adguardvpn_locations(
        run_adguardvpn_cli(config, ["list-locations", str(safe_limit)])
    )
    with STATE_LOCK:
        STATE["last_vpn_locations"] = result
    return result


def connect_adguardvpn(config: dict[str, Any], location: str | None = None) -> dict[str, Any]:
    args = ["connect"]
    if location:
        args.extend(["-l", location])
    result = run_adguardvpn_cli(config, args)
    status = get_adguardvpn_status(config)
    if status.get("connected") and status.get("location"):
        write_last_good_location(config, status["location"])
    payload = {
        **result,
        "location": location,
        "status": status,
    }
    with STATE_LOCK:
        STATE["last_cli_action"] = payload
    return payload


def disconnect_adguardvpn(config: dict[str, Any]) -> dict[str, Any]:
    result = run_adguardvpn_cli(config, ["disconnect"])
    payload = {
        **result,
        "status": get_adguardvpn_status(config),
    }
    with STATE_LOCK:
        STATE["last_cli_action"] = payload
    return payload


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def render_autostart_start_script(config: dict[str, Any]) -> str:
    autostart = config["autostart"]
    return "\n".join(
        [
            "#!/opt/bin/sh",
            "",
            f'APP_DIR={shlex.quote(autostart["app_dir"])}',
            f'PYTHON_BIN={shlex.quote(autostart["python_bin"])}',
            f'LOG_FILE={shlex.quote(autostart["log_file"])}',
            "",
            'cd "$APP_DIR" || exit 1',
            "",
            'exec "$PYTHON_BIN" vpn_panel_server.py >> "$LOG_FILE" 2>&1',
            "",
        ]
    )


def render_autostart_init_script(config: dict[str, Any]) -> str:
    autostart = config["autostart"]
    return "\n".join(
        [
            "#!/opt/bin/sh",
            "",
            f'NAME={shlex.quote(autostart["service_name"])}',
            f'APP_DIR={shlex.quote(autostart["app_dir"])}',
            f'START_SCRIPT={shlex.quote(autostart["start_script_path"])}',
            f'PID_FILE={shlex.quote(autostart["pid_file"])}',
            "",
            "start() {",
            '  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then',
            '    echo "$NAME already running"',
            "    return 0",
            "  fi",
            "",
            "  mkdir -p /opt/var/run",
            '  "$START_SCRIPT" &',
            "  echo $! > \"$PID_FILE\"",
            '  echo "$NAME started"',
            "}",
            "",
            "stop() {",
            '  if [ ! -f "$PID_FILE" ]; then',
            '    echo "$NAME is not running"',
            "    return 0",
            "  fi",
            "",
            '  PID="$(cat "$PID_FILE" 2>/dev/null)"',
            '  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then',
            '    kill "$PID"',
            "  fi",
            "",
            '  rm -f "$PID_FILE"',
            '  echo "$NAME stopped"',
            "}",
            "",
            "status() {",
            '  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then',
            '    echo "$NAME is running with PID $(cat "$PID_FILE")"',
            "    return 0",
            "  fi",
            "",
            '  echo "$NAME is not running"',
            "  return 1",
            "}",
            "",
            'case "$1" in',
            "  start)",
            "    start",
            "    ;;",
            "  stop)",
            "    stop",
            "    ;;",
            "  restart)",
            "    stop",
            "    sleep 1",
            "    start",
            "    ;;",
            "  status)",
            "    status",
            "    ;;",
            "  *)",
            '    echo "Usage: $0 {start|stop|restart|status}"',
            "    exit 1",
            "    ;;",
            "esac",
            "",
        ]
    )


def get_autostart_status(config: dict[str, Any]) -> dict[str, Any]:
    autostart = config["autostart"]
    start_script = Path(autostart["start_script_path"])
    init_script = Path(autostart["init_script_path"])
    pid_file = Path(autostart["pid_file"])
    running = False
    pid: int | None = None
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8", errors="replace").strip())
            running = pid > 0 and Path(f"/proc/{pid}").exists()
        except (OSError, ValueError):
            running = False

    return {
        "enabled": bool(autostart.get("enabled", False)),
        "service_name": autostart["service_name"],
        "app_dir": autostart["app_dir"],
        "python_bin": autostart["python_bin"],
        "start_script_path": str(start_script),
        "init_script_path": str(init_script),
        "pid_file": str(pid_file),
        "start_script_exists": start_script.exists(),
        "init_script_exists": init_script.exists(),
        "pid_file_exists": pid_file.exists(),
        "running": running,
        "pid": pid,
    }


def apply_autostart(config: dict[str, Any], start_now: bool = False) -> dict[str, Any]:
    autostart = config["autostart"]
    start_script = Path(autostart["start_script_path"])
    init_script = Path(autostart["init_script_path"])

    ensure_parent_dir(start_script)
    ensure_parent_dir(init_script)

    start_script.write_text(render_autostart_start_script(config), encoding="utf-8", newline="\n")
    init_script.write_text(render_autostart_init_script(config), encoding="utf-8", newline="\n")
    try:
        start_script.chmod(start_script.stat().st_mode | 0o111)
        init_script.chmod(init_script.stat().st_mode | 0o111)
    except OSError:
        pass

    service_result: dict[str, Any] | None = None
    should_start = start_now or bool(autostart.get("enabled", False))
    if should_start and command_exists(str(init_script)):
        try:
            completed = subprocess.run(
                [str(init_script), "restart"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            service_result = {
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "success": completed.returncode == 0,
            }
        except subprocess.TimeoutExpired as exc:
            service_result = {
                "returncode": None,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "success": False,
            }

    payload = {
        "success": True if service_result is None else service_result["success"],
        "message": "Файлы автозапуска обновлены.",
        "applied_at": utc_now(),
        "service_result": service_result,
        "status": get_autostart_status(config),
    }
    with STATE_LOCK:
        STATE["last_autostart_action"] = payload
    return payload


def remove_autostart(config: dict[str, Any], stop_now: bool = True) -> dict[str, Any]:
    autostart = config["autostart"]
    init_script = Path(autostart["init_script_path"])
    start_script = Path(autostart["start_script_path"])
    service_result: dict[str, Any] | None = None

    if stop_now and init_script.exists():
        try:
            completed = subprocess.run(
                [str(init_script), "stop"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            service_result = {
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "success": completed.returncode == 0,
            }
        except subprocess.TimeoutExpired as exc:
            service_result = {
                "returncode": None,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "success": False,
            }

    for path in (init_script, start_script):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass

    payload = {
        "success": True if service_result is None else service_result["success"],
        "message": "Файлы автозапуска удалены.",
        "removed_at": utc_now(),
        "service_result": service_result,
        "status": get_autostart_status(config),
    }
    with STATE_LOCK:
        STATE["last_autostart_action"] = payload
    return payload


def collect_state(config: dict[str, Any]) -> dict[str, Any]:
    generated_path = resolve_local_path(config["panel"]["generated_script"])
    source_path = resolve_local_path(config["panel"]["source_script"])
    log_path = Path(config["paths"]["log_file"])

    with STATE_LOCK:
        snapshot = deep_copy(STATE)

    last_good_location = read_last_good_location(config)
    if not last_good_location:
        last_status = snapshot.get("last_vpn_status") or {}
        last_good_location = last_status.get("location")

    return {
        "config_path": str(CONFIG_PATH),
        "panel_url": f"http://{config['panel']['host']}:{config['panel']['port']}",
        "source_script": {
            "path": str(source_path),
            "exists": source_path.exists(),
        },
        "generated_script": {
            "path": str(generated_path),
            "exists": generated_path.exists(),
            "size": generated_path.stat().st_size if generated_path.exists() else 0,
        },
        "log_file": {
            "path": str(log_path),
            "exists": log_path.exists(),
            "size": log_path.stat().st_size if log_path.exists() else 0,
        },
        "resource_count": len(config.get("resources", {}).get("links", [])),
        "last_good_location": last_good_location,
        "last_check": snapshot.get("last_check"),
        "last_rotation": snapshot.get("last_rotation"),
        "last_script_generation": snapshot.get("last_script_generation"),
        "last_cli_action": snapshot.get("last_cli_action"),
        "last_vpn_status": snapshot.get("last_vpn_status"),
        "last_autostart_action": snapshot.get("last_autostart_action"),
    }


class PanelHandler(BaseHTTPRequestHandler):
    server_version = "KeeneticVpnPanel/1.0"

    def do_GET(self) -> None:  # noqa: N802
        try:
            if self.path in ("/", "/index.html"):
                return self.serve_static("index.html", "text/html; charset=utf-8")
            if self.path == "/settings.html":
                return self.serve_static("settings.html", "text/html; charset=utf-8")
            if self.path == "/logs.html":
                return self.serve_static("logs.html", "text/html; charset=utf-8")
            if self.path == "/script.html":
                return self.serve_static("script.html", "text/html; charset=utf-8")
            if self.path == "/styles.css":
                return self.serve_static("styles.css", "text/css; charset=utf-8")
            if self.path == "/app.js":
                return self.serve_static("app.js", "application/javascript; charset=utf-8")
            if self.path == "/api/config":
                return self.send_json(load_config())
            if self.path == "/api/state":
                return self.send_json(collect_state(load_config()))
            if self.path == "/api/adguardvpn/status":
                return self.send_json(get_adguardvpn_status(load_config()))
            if self.path == "/api/adguardvpn/locations":
                return self.send_json(get_adguardvpn_locations(load_config()))
            if self.path == "/api/autostart/status":
                return self.send_json(get_autostart_status(load_config()))
            if self.path == "/api/script":
                config = load_config()
                script_path = resolve_local_path(config["panel"]["generated_script"])
                content = script_path.read_text(encoding="utf-8") if script_path.exists() else render_script(config)
                return self.send_json({"content": content})
            if self.path.startswith("/api/logs"):
                config = load_config()
                log_path = Path(config["paths"]["log_file"])
                return self.send_json(
                    {
                        "content": tail_file(log_path, 200),
                        "path": str(log_path),
                        "exists": log_path.exists(),
                    }
                )

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self.read_json()
            if self.path == "/api/config":
                config = validate_config(body)
                write_config(config)
                generation = generate_script(config)
                return self.send_json({"config": config, "generation": generation})
            if self.path == "/api/actions/generate-script":
                return self.send_json(generate_script(load_config()))
            if self.path == "/api/actions/check":
                return self.send_json(perform_http_check(load_config()))
            if self.path == "/api/actions/rotate":
                return self.send_json(run_rotation(load_config()))
            if self.path == "/api/adguardvpn/connect":
                location = str(body.get("location", "")).strip() or None
                return self.send_json(connect_adguardvpn(load_config(), location))
            if self.path == "/api/adguardvpn/disconnect":
                return self.send_json(disconnect_adguardvpn(load_config()))
            if self.path == "/api/autostart/apply":
                start_now = bool(body.get("start_now", False))
                return self.send_json(apply_autostart(load_config(), start_now=start_now))
            if self.path == "/api/autostart/remove":
                stop_now = bool(body.get("stop_now", True))
                return self.send_json(remove_autostart(load_config(), stop_now=stop_now))

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_static(self, filename: str, content_type: str) -> None:
        path = WEB_DIR / filename
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    config = ensure_config()
    generate_script(config)
    host = config["panel"]["host"]
    port = config["panel"]["port"]
    server = ThreadingHTTPServer((host, port), PanelHandler)
    print(f"VPN panel running on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
