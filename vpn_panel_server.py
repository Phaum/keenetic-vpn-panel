from __future__ import annotations

import json
import os
import ipaddress
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
ASSETS_DIR = BASE_DIR / "assets"
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
    "automation": {
        "enabled": False,
        "check_interval": 600,
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
    "transparent_proxy": {
        "mode": "router-only",
        "enabled": False,
        "proxy_type": "auto",
        "proxy_host": "127.0.0.1",
        "proxy_port": 1080,
        "listen_ip": "127.0.0.1",
        "listen_port": 12345,
        "redsocks_bin": "redsocks",
        "redsocks_pid_file": "generated/redsocks.pid",
        "redsocks_config_path": "generated/redsocks.conf",
        "iptables_path": "iptables",
        "chain_name": "KVPN_REDSOCKS",
        "target_subnets": "192.168.1.0/24",
        "bypass_subnets": "0.0.0.0/8, 10.0.0.0/8, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16, 224.0.0.0/4, 240.0.0.0/4",
        "destination_subnets": "",
        "destination_domains": "",
        "ipset_path": "ipset",
        "destination_subnet_set": "KVPN_DST_NET",
        "destination_domain_set": "KVPN_DST_DNS",
        "dnsmasq_ipset_config_path": "generated/dnsmasq-ipset-kvpn.conf",
        "dnsmasq_restart_command": "",
        "ip_path": "ip",
        "tun_interface": "auto",
        "tun_route_table": 246,
        "tun_fwmark": 246,
        "tun_rule_priority": 12460,
        "dns_hijack_enabled": True,
        "dns_hijack_port": 53,
        "rules_script_path": "generated/apply-transparent-proxy.sh",
        "stop_script_path": "generated/remove-transparent-proxy.sh",
    },
    "paths": {
        "lock_file": "/opt/tmp/adguardvpn-switch.lock",
        "log_file": "/opt/var/log/adguardvpn-rotate.log",
        "good_file": "/opt/tmp/adguardvpn-good-location.txt",
        "tmp_file": "/opt/tmp/adguardvpn-locations.txt",
        "body_file": "/opt/tmp/adguardvpn-check-body.txt",
    },
    "logging": {
        "debug_enabled": False,
        "debug_log_file": "/opt/var/log/adguardvpn-rotate.debug.log",
        "debug_max_bytes": 262144,
        "debug_backup_count": 2,
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
                "name": "Keenetic NFQWS 2",
                "url": "http://192.168.1.1:90",
                "description": "Router Zapret",
                "group": "VPN",
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
VPN_COMMAND_LOCK = threading.Lock()
AUTOMATION_WAKE_EVENT = threading.Event()
STATE: dict[str, Any] = {
    "last_check": None,
    "last_rotation": None,
    "last_automation_action": None,
    "last_script_generation": None,
    "last_cli_action": None,
    "last_vpn_status": None,
    "last_vpn_locations": None,
    "last_transparent_proxy_action": None,
    "last_transparent_proxy_status": None,
    "last_autostart_action": None,
    "last_update_action": None,
    "automation_runtime": {
        "thread_alive": False,
        "loop_running": False,
        "thread_started_at": None,
        "last_started_at": None,
        "last_completed_at": None,
        "next_check_at": None,
        "last_error": None,
        "last_result": None,
        "current_interval": None,
    },
}

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
TRANSPARENT_PROXY_TYPES = {"auto", "socks5", "http-connect"}
TRANSPARENT_PROXY_MODES = {"router-only", "transparent-redsocks", "tun-policy"}
ROUTER_ENV = {
    "SSL_CERT_FILE": "/opt/etc/ssl/certs/ca-certificates.crt",
    "HOME": "/opt/home/admin",
    "PATH": "/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def deep_copy(data: Any) -> Any:
    return json.loads(json.dumps(data))


def notify_automation_config_changed() -> None:
    AUTOMATION_WAKE_EVENT.set()


def update_automation_runtime(**updates: Any) -> None:
    with STATE_LOCK:
        runtime = STATE.setdefault("automation_runtime", {})
        runtime.update(updates)


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


def backup_config_snapshot(content: str, suffix: str) -> Path | None:
    backup_path = CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.{suffix}")
    try:
        if not backup_path.exists():
            backup_path.write_text(content, encoding="utf-8")
        return backup_path
    except OSError:
        return None


def decode_config_text(text: str) -> tuple[dict[str, Any], bool]:
    try:
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("config.json root must be an object")
        return payload, False
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        stripped = text.lstrip()
        payload, end = decoder.raw_decode(stripped)
        if not isinstance(payload, dict):
            raise ValueError("config.json root must be an object")
        trailing = stripped[end:].strip()
        return payload, bool(trailing)


def load_config() -> dict[str, Any]:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    try:
        raw, recovered = decode_config_text(text)
    except Exception:
        backup_config_snapshot(text, "invalid.backup")
        source = BASE_DIR / DEFAULT_CONFIG["panel"]["source_script"]
        raw = import_from_shell_script(source)
        write_config(raw)
        return merge_defaults(DEFAULT_CONFIG, raw)

    merged = merge_defaults(DEFAULT_CONFIG, raw)
    if recovered:
        backup_config_snapshot(text, "recovered.backup")
        write_config(merged)
    return merged


def ensure_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        return load_config()

    source = BASE_DIR / DEFAULT_CONFIG["panel"]["source_script"]
    config = import_from_shell_script(source)
    write_config(config)
    return config


def parse_csv_items(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = [str(item).strip() for item in value]
    else:
        raw_items = [part.strip() for part in re.split(r"[\r\n,]+", str(value or ""))]
    return [item for item in raw_items if item]


def normalize_csv_items(value: Any) -> str:
    items = parse_csv_items(value)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        lowered = item.casefold()
        if lowered in seen:
            continue
        deduped.append(item)
        seen.add(lowered)
    return ", ".join(deduped)


def normalize_network_items(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    items = parse_csv_items(value)
    if not items:
        if allow_empty:
            return ""
        raise ValueError(f"Field '{field_name}' must contain at least one subnet")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        try:
            subnet = str(ipaddress.ip_network(item, strict=False))
        except ValueError as exc:
            raise ValueError(f"Field '{field_name}' contains invalid subnet '{item}'") from exc
        if subnet in seen:
            continue
        normalized.append(subnet)
        seen.add(subnet)
    return ", ".join(normalized)


def normalize_domain_items(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    items = parse_csv_items(value)
    if not items:
        if allow_empty:
            return ""
        raise ValueError(f"Field '{field_name}' must contain at least one domain")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        domain = item.strip().lower().rstrip(".")
        if domain.startswith("*."):
            domain = domain[2:]
        if not domain:
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9]", domain):
            raise ValueError(f"Field '{field_name}' contains invalid domain '{item}'")
        if ".." in domain:
            raise ValueError(f"Field '{field_name}' contains invalid domain '{item}'")
        if domain in seen:
            continue
        normalized.append(domain)
        seen.add(domain)

    if not normalized and not allow_empty:
        raise ValueError(f"Field '{field_name}' must contain at least one domain")
    return ", ".join(normalized)


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
        ("transparent_proxy", "mode"),
        ("transparent_proxy", "proxy_type"),
        ("transparent_proxy", "proxy_host"),
        ("transparent_proxy", "listen_ip"),
        ("transparent_proxy", "redsocks_bin"),
        ("transparent_proxy", "redsocks_pid_file"),
        ("transparent_proxy", "redsocks_config_path"),
        ("transparent_proxy", "iptables_path"),
        ("transparent_proxy", "ipset_path"),
        ("transparent_proxy", "chain_name"),
        ("transparent_proxy", "destination_subnet_set"),
        ("transparent_proxy", "destination_domain_set"),
        ("transparent_proxy", "target_subnets"),
        ("transparent_proxy", "bypass_subnets"),
        ("transparent_proxy", "dnsmasq_ipset_config_path"),
        ("transparent_proxy", "rules_script_path"),
        ("transparent_proxy", "stop_script_path"),
        ("transparent_proxy", "ip_path"),
        ("transparent_proxy", "tun_interface"),
        ("vpn", "test_url"),
        ("vpn", "expected_text"),
        ("paths", "lock_file"),
        ("paths", "log_file"),
        ("paths", "good_file"),
        ("paths", "tmp_file"),
        ("paths", "body_file"),
        ("logging", "debug_log_file"),
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
        ("transparent_proxy", "proxy_port"),
        ("transparent_proxy", "listen_port"),
        ("transparent_proxy", "tun_route_table"),
        ("transparent_proxy", "tun_fwmark"),
        ("transparent_proxy", "tun_rule_priority"),
        ("transparent_proxy", "dns_hijack_port"),
        ("automation", "check_interval"),
        ("vpn", "top_count"),
        ("vpn", "timeout"),
        ("vpn", "connect_timeout"),
        ("vpn", "check_retries"),
        ("vpn", "check_retry_delay"),
        ("vpn", "switch_delay"),
        ("logging", "debug_max_bytes"),
        ("logging", "debug_backup_count"),
    ]

    for section, key in positive_int_fields:
        try:
            value = int(merged[section][key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Field '{section}.{key}' must be an integer") from exc
        if value <= 0:
            raise ValueError(f"Field '{section}.{key}' must be greater than zero")
        merged[section][key] = value

    merged["automation"]["enabled"] = bool(merged.get("automation", {}).get("enabled", False))
    merged["autostart"]["enabled"] = bool(merged.get("autostart", {}).get("enabled", False))
    merged["logging"]["debug_enabled"] = bool(merged.get("logging", {}).get("debug_enabled", False))

    transparent_proxy = merged["transparent_proxy"]
    mode_raw = str(transparent_proxy.get("mode", "")).strip().lower()
    if not mode_raw:
        mode_raw = "transparent-redsocks" if bool(transparent_proxy.get("enabled", False)) else "router-only"
    if mode_raw not in TRANSPARENT_PROXY_MODES:
        raise ValueError(
            "Field 'transparent_proxy.mode' must be one of: router-only, transparent-redsocks"
        )
    transparent_proxy["mode"] = mode_raw
    transparent_proxy["enabled"] = mode_raw in {"transparent-redsocks", "tun-policy"}

    proxy_type = str(transparent_proxy.get("proxy_type", "auto")).strip().lower()
    if proxy_type not in TRANSPARENT_PROXY_TYPES:
        raise ValueError(
            "Field 'transparent_proxy.proxy_type' must be one of: auto, socks5, http-connect"
        )
    transparent_proxy["proxy_type"] = proxy_type

    chain_name = str(transparent_proxy.get("chain_name", "")).strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,27}", chain_name):
        raise ValueError(
            "Field 'transparent_proxy.chain_name' must start with a letter, contain only A-Z, 0-9, _ and be at most 28 chars"
        )
    transparent_proxy["chain_name"] = chain_name

    for key in ("destination_subnet_set", "destination_domain_set"):
        set_name = str(transparent_proxy.get(key, "")).strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,30}", set_name):
            raise ValueError(
                f"Field 'transparent_proxy.{key}' must start with a letter, contain only A-Z, 0-9, _ and be at most 31 chars"
            )
        transparent_proxy[key] = set_name

    transparent_proxy["target_subnets"] = normalize_network_items(
        transparent_proxy.get("target_subnets", ""),
        "transparent_proxy.target_subnets",
    )
    transparent_proxy["bypass_subnets"] = normalize_network_items(
        transparent_proxy.get("bypass_subnets", ""),
        "transparent_proxy.bypass_subnets",
        allow_empty=True,
    )
    transparent_proxy["destination_subnets"] = normalize_network_items(
        transparent_proxy.get("destination_subnets", ""),
        "transparent_proxy.destination_subnets",
        allow_empty=True,
    )
    transparent_proxy["destination_domains"] = normalize_domain_items(
        transparent_proxy.get("destination_domains", ""),
        "transparent_proxy.destination_domains",
        allow_empty=True,
    )
    transparent_proxy["dnsmasq_restart_command"] = str(
        transparent_proxy.get("dnsmasq_restart_command", "")
    ).strip()
    transparent_proxy["dns_hijack_enabled"] = bool(transparent_proxy.get("dns_hijack_enabled", False))

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
    content = TEMPLATE_PATH.read_text(encoding="utf-8")
    replacements = {
        "python_bin": shlex.quote(config["autostart"]["python_bin"]),
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
        "transparent_proxy": generate_transparent_proxy_artifacts(config),
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


def build_command_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(ROUTER_ENV)
    return env


def is_private_ipv4(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 4 or not all(part.isdigit() for part in parts):
        return False
    octets = [int(part) for part in parts]
    if octets[0] == 10:
        return True
    if octets[0] == 192 and octets[1] == 168:
        return True
    if octets[0] == 172 and 16 <= octets[1] <= 31:
        return True
    return False


def detect_lan_ipv4() -> str | None:
    if shutil.which("ip"):
        try:
            completed = subprocess.run(
                ["ip", "-4", "-o", "addr", "show", "up"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            candidates: list[str] = []
            for line in completed.stdout.splitlines():
                match = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+)/", line)
                if not match:
                    continue
                ip = match.group(1)
                if ip.startswith("127."):
                    continue
                if is_private_ipv4(ip):
                    candidates.append(ip)
            if candidates:
                candidates.sort(
                    key=lambda ip: (
                        0 if ip.startswith("192.168.") else 1 if ip.startswith("10.") else 2,
                        ip,
                    )
                )
                return candidates[0]
        except (OSError, subprocess.SubprocessError):
            pass

    try:
        hostname_ip = socket.gethostbyname(socket.gethostname())
        if hostname_ip and not hostname_ip.startswith("127.") and is_private_ipv4(hostname_ip):
            return hostname_ip
    except OSError:
        pass

    return None


def get_panel_access_host(config: dict[str, Any]) -> str:
    host = str(config["panel"]["host"]).strip()
    if host and host not in {"0.0.0.0", "::", "127.0.0.1", "localhost"}:
        return host
    return detect_lan_ipv4() or "192.168.1.1"


def ensure_runtime_dirs(config: dict[str, Any]) -> None:
    for key in ("lock_file", "log_file", "good_file", "tmp_file", "body_file"):
        try:
            Path(config["paths"][key]).parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
    try:
        Path(config["logging"]["debug_log_file"]).parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    for key in (
        "redsocks_pid_file",
        "redsocks_config_path",
        "dnsmasq_ipset_config_path",
        "rules_script_path",
        "stop_script_path",
    ):
        try:
            resolve_local_path(config["transparent_proxy"][key]).parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue


def get_automation_status(config: dict[str, Any]) -> dict[str, Any]:
    with STATE_LOCK:
        runtime = deep_copy(STATE.get("automation_runtime") or {})
        last_action = deep_copy(STATE.get("last_automation_action"))

    return {
        "enabled": bool(config["automation"]["enabled"]),
        "check_interval": int(config["automation"]["check_interval"]),
        "thread_alive": bool(runtime.get("thread_alive")),
        "loop_running": bool(runtime.get("loop_running")),
        "thread_started_at": runtime.get("thread_started_at"),
        "last_started_at": runtime.get("last_started_at"),
        "last_completed_at": runtime.get("last_completed_at"),
        "next_check_at": runtime.get("next_check_at"),
        "last_error": runtime.get("last_error"),
        "last_result": runtime.get("last_result"),
        "current_interval": runtime.get("current_interval"),
        "last_action": last_action,
    }


def append_rotation_log(config: dict[str, Any], message: str) -> None:
    log_path = Path(config["paths"]["log_file"])
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        return


def summarize_for_log(value: Any, max_length: int = 600) -> Any:
    if isinstance(value, str):
        compact = strip_ansi(value).replace("\r", "").strip()
        compact = compact.replace("\n", "\\n")
        return compact[: max_length - 3] + "..." if len(compact) > max_length else compact
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): summarize_for_log(item, max_length=max_length) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [summarize_for_log(item, max_length=max_length) for item in value]
    return value


def rotate_debug_logs(config: dict[str, Any]) -> None:
    logging_cfg = config["logging"]
    log_path = Path(logging_cfg["debug_log_file"])
    max_bytes = int(logging_cfg["debug_max_bytes"])
    backup_count = int(logging_cfg["debug_backup_count"])
    if not log_path.exists() or max_bytes <= 0 or log_path.stat().st_size < max_bytes:
        return

    for index in range(backup_count, 0, -1):
        source = log_path.with_name(f"{log_path.name}.{index}")
        target = log_path.with_name(f"{log_path.name}.{index + 1}")
        try:
            if index == backup_count and source.exists():
                source.unlink()
            elif source.exists():
                source.replace(target)
        except OSError:
            return

    try:
        log_path.replace(log_path.with_name(f"{log_path.name}.1"))
    except OSError:
        return


def append_debug_log(config: dict[str, Any], event: str, **data: Any) -> None:
    logging_cfg = config["logging"]
    if not logging_cfg.get("debug_enabled"):
        return

    ensure_runtime_dirs(config)
    rotate_debug_logs(config)
    log_path = Path(logging_cfg["debug_log_file"])
    payload = {
        "ts": utc_now(),
        "pid": os.getpid(),
        "event": event,
        "data": summarize_for_log(data),
    }
    try:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        return


def update_last_check_state(result: dict[str, Any]) -> None:
    with STATE_LOCK:
        STATE["last_check"] = result


def normalize_location_name(value: str | None) -> str:
    return strip_ansi(value or "").replace("\r", "").strip()


def same_location(left: str | None, right: str | None) -> bool:
    return bool(normalize_location_name(left)) and normalize_location_name(left).casefold() == normalize_location_name(right).casefold()


def process_is_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False

    proc_path = Path(f"/proc/{pid}")
    if proc_path.exists():
        return True

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_rotation_file_lock(config: dict[str, Any]) -> tuple[bool, int | None]:
    ensure_runtime_dirs(config)
    lock_path = Path(config["paths"]["lock_file"])
    stale_pid: int | None = None
    if lock_path.exists():
        try:
            stale_pid = int(lock_path.read_text(encoding="utf-8", errors="replace").strip())
        except (OSError, ValueError):
            stale_pid = None
        if process_is_running(stale_pid):
            append_debug_log(config, "rotation.lock.busy", active_pid=stale_pid)
            return False, stale_pid

    try:
        lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
    except OSError:
        append_debug_log(config, "rotation.lock.error", path=str(lock_path))
        return False, None
    append_debug_log(config, "rotation.lock.acquired", path=str(lock_path))
    return True, stale_pid


def release_rotation_file_lock(config: dict[str, Any]) -> None:
    for key in ("lock_file", "tmp_file", "body_file"):
        path = Path(config["paths"][key])
        try:
            if path.exists():
                path.unlink()
        except OSError:
            continue
    append_debug_log(config, "rotation.lock.released")


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


def write_text_file(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    if executable:
        try:
            path.chmod(path.stat().st_mode | 0o111)
        except OSError:
            pass


def run_managed_command(
    config: dict[str, Any],
    command: list[str],
    *,
    timeout: int = 30,
    event: str,
) -> dict[str, Any]:
    append_debug_log(config, f"{event}.started", command=command, timeout=timeout)
    if not command or not command_exists(command[0]):
        result = {
            "success": False,
            "message": f"Команда '{command[0] if command else ''}' не найдена.",
            "executed_at": utc_now(),
            "stdout": "",
            "stderr": "",
            "returncode": None,
            "command": command,
        }
        append_debug_log(config, f"{event}.missing", result=result)
        return result

    try:
        completed = subprocess.run(
            command,
            cwd=str(BASE_DIR),
            env=build_command_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        result = {
            "success": completed.returncode == 0,
            "message": "Команда выполнена." if completed.returncode == 0 else "Команда завершилась с ошибкой.",
            "executed_at": utc_now(),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
            "command": command,
        }
        append_debug_log(config, f"{event}.completed", result=result)
        return result
    except subprocess.TimeoutExpired as exc:
        result = {
            "success": False,
            "message": "Команда превысила таймаут.",
            "executed_at": utc_now(),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "returncode": None,
            "command": command,
        }
        append_debug_log(config, f"{event}.timeout", result=result)
        return result


def run_shell_text_command(
    config: dict[str, Any],
    command_text: str,
    *,
    timeout: int,
    event: str,
) -> dict[str, Any]:
    return run_managed_command(
        config,
        ["sh", "-c", command_text],
        timeout=timeout,
        event=event,
    )


def parse_listener_endpoint(listener: str | None) -> dict[str, Any] | None:
    text = strip_ansi(listener or "").strip()
    if not text:
        return None

    match = re.search(
        r"(?:(?P<scheme>[a-z][a-z0-9+.-]*)://)?(?P<host>\[[^\]]+\]|[^:\s]+):(?P<port>\d+)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    host = match.group("host").strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return {
        "scheme": (match.group("scheme") or "").lower() or None,
        "host": host,
        "port": int(match.group("port")),
    }


def infer_transparent_proxy_type(config: dict[str, Any], vpn_status: dict[str, Any] | None = None) -> str:
    configured = str(config["transparent_proxy"].get("proxy_type", "auto")).strip().lower()
    if configured in {"socks5", "http-connect"}:
        return configured

    lowered_mode = str((vpn_status or {}).get("mode") or "").strip().lower()
    if "http" in lowered_mode:
        return "http-connect"
    return "socks5"


def prepare_adguardvpn_transport(config: dict[str, Any]) -> dict[str, Any]:
    mode = str(config["transparent_proxy"].get("mode", "router-only")).strip().lower()
    steps: list[dict[str, Any]] = []

    if mode == "transparent-redsocks":
        steps.append(run_adguardvpn_cli(config, ["config", "set-mode", "SOCKS"]))
    elif mode == "tun-policy":
        steps.append(run_adguardvpn_cli(config, ["config", "set-mode", "TUN"]))
        steps.append(run_adguardvpn_cli(config, ["config", "set-tun-routing-mode", "NONE"]))
    else:
        return {
            "success": True,
            "mode": mode,
            "steps": [],
            "message": "Дополнительная настройка transport mode не требуется.",
            "executed_at": utc_now(),
        }

    success = all(step.get("success") for step in steps)
    return {
        "success": success,
        "mode": mode,
        "steps": steps,
        "message": "Transport mode подготовлен." if success else "Не удалось подготовить transport mode.",
        "executed_at": utc_now(),
    }


def resolve_transparent_proxy_upstream(
    config: dict[str, Any],
    vpn_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    transparent_proxy = config["transparent_proxy"]
    endpoint = parse_listener_endpoint((vpn_status or {}).get("listener"))
    host = transparent_proxy["proxy_host"]
    port = int(transparent_proxy["proxy_port"])
    source = "config"
    if endpoint:
        host = endpoint["host"]
        port = endpoint["port"]
        source = "vpn_status.listener"

    if not host or port <= 0:
        raise ValueError("Не удалось определить upstream-прокси для transparent proxy.")

    return {
        "host": host,
        "port": port,
        "type": infer_transparent_proxy_type(config, vpn_status),
        "source": source,
        "listener": (vpn_status or {}).get("listener"),
        "mode": (vpn_status or {}).get("mode"),
    }


def has_selective_targets(config: dict[str, Any]) -> bool:
    transparent_proxy = config["transparent_proxy"]
    return bool(
        parse_csv_items(transparent_proxy.get("destination_subnets", ""))
        or parse_csv_items(transparent_proxy.get("destination_domains", ""))
    )


def transparent_proxy_uses_redsocks(config: dict[str, Any]) -> bool:
    return str(config["transparent_proxy"].get("mode", "")).strip().lower() == "transparent-redsocks"


def transparent_proxy_uses_tun(config: dict[str, Any]) -> bool:
    return str(config["transparent_proxy"].get("mode", "")).strip().lower() == "tun-policy"


def render_dnsmasq_ipset_config(config: dict[str, Any]) -> str:
    transparent_proxy = config["transparent_proxy"]
    if not transparent_proxy.get("enabled"):
        return ""
    domain_set = transparent_proxy["destination_domain_set"]
    domains = parse_csv_items(transparent_proxy.get("destination_domains", ""))
    if not domains:
        return ""
    lines = [
        "# Generated by keenetic-vpn-panel",
        "# dnsmasq must be restarted to load updated config files.",
    ]
    lines.extend([f"ipset=/{domain}/{domain_set}" for domain in domains])
    return "\n".join(lines) + "\n"


def render_tun_policy_apply_script(config: dict[str, Any]) -> str:
    transparent_proxy = config["transparent_proxy"]
    bypass_subnets = parse_csv_items(transparent_proxy["bypass_subnets"])
    target_subnets = parse_csv_items(transparent_proxy["target_subnets"])
    destination_subnets = parse_csv_items(transparent_proxy.get("destination_subnets", ""))
    destination_domains = parse_csv_items(transparent_proxy.get("destination_domains", ""))
    selective_mode = bool(destination_subnets or destination_domains)
    dns_hijack_enabled = bool(transparent_proxy.get("dns_hijack_enabled", False))
    lines = [
        "#!/opt/bin/sh",
        "",
        "set -eu",
        "",
        f'IP={shlex.quote(transparent_proxy["ip_path"])}',
        f'IPTABLES={shlex.quote(transparent_proxy["iptables_path"])}',
        f'IPSET={shlex.quote(transparent_proxy["ipset_path"])}',
        f'MANGLE_CHAIN={shlex.quote(transparent_proxy["chain_name"])}',
        f'DNS_CHAIN={shlex.quote(transparent_proxy["chain_name"] + "_DNS")}',
        f'DEST_NET_SET={shlex.quote(transparent_proxy["destination_subnet_set"])}',
        f'DEST_DOMAIN_SET={shlex.quote(transparent_proxy["destination_domain_set"])}',
        f'ROUTE_TABLE={int(transparent_proxy["tun_route_table"])}',
        f'FWMARK={int(transparent_proxy["tun_fwmark"])}',
        f'RULE_PRIORITY={int(transparent_proxy["tun_rule_priority"])}',
        f'TUN_IFACE_CONFIG={shlex.quote(transparent_proxy["tun_interface"])}',
        f'DNS_PORT={int(transparent_proxy["dns_hijack_port"])}',
        "",
        'detect_tun_iface() {',
        '  if [ -n "$TUN_IFACE_CONFIG" ] && [ "$TUN_IFACE_CONFIG" != "auto" ]; then',
        '    echo "$TUN_IFACE_CONFIG"',
        "    return 0",
        "  fi",
        '  CANDIDATES="$($IP -o link show up 2>/dev/null | awk -F\': \' \'{print $2}\' | sed \'s/@.*//\' | grep -E \'^(adg|tun|tap|wg|utun)\' || true)"',
        '  COUNT="$(printf "%s\\n" "$CANDIDATES" | awk \'NF {count += 1} END {print count + 0}\')"',
        '  if [ "$COUNT" -eq 1 ]; then',
        '    printf "%s\\n" "$CANDIDATES" | awk \'NF {print; exit}\'',
        "    return 0",
        "  fi",
        '  CANDIDATES="$($IP -o addr show up scope global 2>/dev/null | awk \'{print $2}\' | sed \'s/@.*//\' | sort -u | grep -E \'^(adg|tun|tap|wg|utun)\' || true)"',
        '  printf "%s\\n" "$CANDIDATES" | awk \'NF {print; exit}\'',
        "}",
        "",
        'TUN_IFACE="$(detect_tun_iface)"',
        'if [ -z "$TUN_IFACE" ]; then',
        '  echo "Could not detect TUN interface. Set transparent_proxy.tun_interface explicitly." >&2',
        "  exit 1",
        "fi",
        "",
        '"$IPSET" create "$DEST_NET_SET" hash:net family inet -exist',
        '"$IPSET" create "$DEST_DOMAIN_SET" hash:ip family inet -exist',
        '"$IPSET" flush "$DEST_NET_SET"',
        '"$IPSET" flush "$DEST_DOMAIN_SET"',
    ]
    for subnet in destination_subnets:
        lines.append(f'"$IPSET" add "$DEST_NET_SET" {shlex.quote(subnet)} -exist')
    lines.extend(
        [
            "",
            '"$IPTABLES" -t mangle -N "$MANGLE_CHAIN" 2>/dev/null || true',
            '"$IPTABLES" -t mangle -F "$MANGLE_CHAIN"',
        ]
    )
    for subnet in bypass_subnets:
        lines.append(f'"$IPTABLES" -t mangle -A "$MANGLE_CHAIN" -d {shlex.quote(subnet)} -j RETURN')
    for subnet in target_subnets:
        if destination_subnets:
            lines.append(
                f'"$IPTABLES" -t mangle -A "$MANGLE_CHAIN" -s {shlex.quote(subnet)} -p tcp -m set --match-set "$DEST_NET_SET" dst -j MARK --set-mark "$FWMARK"'
            )
            lines.append(
                f'"$IPTABLES" -t mangle -A "$MANGLE_CHAIN" -s {shlex.quote(subnet)} -p udp -m set --match-set "$DEST_NET_SET" dst -j MARK --set-mark "$FWMARK"'
            )
        if destination_domains:
            lines.append(
                f'"$IPTABLES" -t mangle -A "$MANGLE_CHAIN" -s {shlex.quote(subnet)} -p tcp -m set --match-set "$DEST_DOMAIN_SET" dst -j MARK --set-mark "$FWMARK"'
            )
            lines.append(
                f'"$IPTABLES" -t mangle -A "$MANGLE_CHAIN" -s {shlex.quote(subnet)} -p udp -m set --match-set "$DEST_DOMAIN_SET" dst -j MARK --set-mark "$FWMARK"'
            )
        if not selective_mode:
            lines.append(
                f'"$IPTABLES" -t mangle -A "$MANGLE_CHAIN" -s {shlex.quote(subnet)} -p tcp -j MARK --set-mark "$FWMARK"'
            )
            lines.append(
                f'"$IPTABLES" -t mangle -A "$MANGLE_CHAIN" -s {shlex.quote(subnet)} -p udp -j MARK --set-mark "$FWMARK"'
            )
    lines.extend(
        [
            'if ! "$IPTABLES" -t mangle -C PREROUTING -j "$MANGLE_CHAIN" 2>/dev/null; then',
            '  "$IPTABLES" -t mangle -A PREROUTING -j "$MANGLE_CHAIN"',
            "fi",
            "",
        ]
    )
    if dns_hijack_enabled:
        lines.extend(
            [
                '"$IPTABLES" -t nat -N "$DNS_CHAIN" 2>/dev/null || true',
                '"$IPTABLES" -t nat -F "$DNS_CHAIN"',
            ]
        )
        for subnet in target_subnets:
            lines.append(
                f'"$IPTABLES" -t nat -A "$DNS_CHAIN" -s {shlex.quote(subnet)} -p udp --dport 53 -j REDIRECT --to-ports "$DNS_PORT"'
            )
            lines.append(
                f'"$IPTABLES" -t nat -A "$DNS_CHAIN" -s {shlex.quote(subnet)} -p tcp --dport 53 -j REDIRECT --to-ports "$DNS_PORT"'
            )
        lines.extend(
            [
                'if ! "$IPTABLES" -t nat -C PREROUTING -j "$DNS_CHAIN" 2>/dev/null; then',
                '  "$IPTABLES" -t nat -A PREROUTING -j "$DNS_CHAIN"',
                "fi",
                "",
            ]
        )
    lines.extend(
        [
            '"$IP" route replace default dev "$TUN_IFACE" table "$ROUTE_TABLE"',
            '"$IP" rule del priority "$RULE_PRIORITY" 2>/dev/null || true',
            '"$IP" rule add fwmark "$FWMARK" priority "$RULE_PRIORITY" table "$ROUTE_TABLE"',
            "",
        ]
    )
    return "\n".join(lines)


def render_tun_policy_stop_script(config: dict[str, Any]) -> str:
    transparent_proxy = config["transparent_proxy"]
    return "\n".join(
        [
            "#!/opt/bin/sh",
            "",
            "set -eu",
            "",
            f'IP={shlex.quote(transparent_proxy["ip_path"])}',
            f'IPTABLES={shlex.quote(transparent_proxy["iptables_path"])}',
            f'IPSET={shlex.quote(transparent_proxy["ipset_path"])}',
            f'MANGLE_CHAIN={shlex.quote(transparent_proxy["chain_name"])}',
            f'DNS_CHAIN={shlex.quote(transparent_proxy["chain_name"] + "_DNS")}',
            f'DEST_NET_SET={shlex.quote(transparent_proxy["destination_subnet_set"])}',
            f'DEST_DOMAIN_SET={shlex.quote(transparent_proxy["destination_domain_set"])}',
            f'ROUTE_TABLE={int(transparent_proxy["tun_route_table"])}',
            f'FWMARK={int(transparent_proxy["tun_fwmark"])}',
            f'RULE_PRIORITY={int(transparent_proxy["tun_rule_priority"])}',
            "",
            'while "$IPTABLES" -t mangle -C PREROUTING -j "$MANGLE_CHAIN" 2>/dev/null; do',
            '  "$IPTABLES" -t mangle -D PREROUTING -j "$MANGLE_CHAIN"',
            "done",
            'while "$IPTABLES" -t nat -C PREROUTING -j "$DNS_CHAIN" 2>/dev/null; do',
            '  "$IPTABLES" -t nat -D PREROUTING -j "$DNS_CHAIN"',
            "done",
            '"$IPTABLES" -t mangle -F "$MANGLE_CHAIN" 2>/dev/null || true',
            '"$IPTABLES" -t mangle -X "$MANGLE_CHAIN" 2>/dev/null || true',
            '"$IPTABLES" -t nat -F "$DNS_CHAIN" 2>/dev/null || true',
            '"$IPTABLES" -t nat -X "$DNS_CHAIN" 2>/dev/null || true',
            '"$IPSET" flush "$DEST_NET_SET" 2>/dev/null || true',
            '"$IPSET" destroy "$DEST_NET_SET" 2>/dev/null || true',
            '"$IPSET" flush "$DEST_DOMAIN_SET" 2>/dev/null || true',
            '"$IPSET" destroy "$DEST_DOMAIN_SET" 2>/dev/null || true',
            '"$IP" rule del priority "$RULE_PRIORITY" 2>/dev/null || true',
            '"$IP" route flush table "$ROUTE_TABLE" 2>/dev/null || true',
            "",
        ]
    )


def render_redsocks_config(config: dict[str, Any], upstream: dict[str, Any]) -> str:
    transparent_proxy = config["transparent_proxy"]
    return "\n".join(
        [
            "base {",
            "  log_debug = off;",
            "  log_info = on;",
            "  daemon = on;",
            "  redirector = iptables;",
            "}",
            "",
            "redsocks {",
            f"  local_ip = {transparent_proxy['listen_ip']};",
            f"  local_port = {int(transparent_proxy['listen_port'])};",
            f"  ip = {upstream['host']};",
            f"  port = {int(upstream['port'])};",
            f"  type = {upstream['type']};",
            "}",
            "",
        ]
    )


def render_transparent_proxy_apply_script(config: dict[str, Any]) -> str:
    if transparent_proxy_uses_tun(config):
        return render_tun_policy_apply_script(config)

    transparent_proxy = config["transparent_proxy"]
    bypass_subnets = parse_csv_items(transparent_proxy["bypass_subnets"])
    target_subnets = parse_csv_items(transparent_proxy["target_subnets"])
    destination_subnets = parse_csv_items(transparent_proxy.get("destination_subnets", ""))
    destination_domains = parse_csv_items(transparent_proxy.get("destination_domains", ""))
    selective_mode = bool(destination_subnets or destination_domains)
    return "\n".join(
        [
            "#!/opt/bin/sh",
            "",
            "set -eu",
            "",
            f'IPTABLES={shlex.quote(transparent_proxy["iptables_path"])}',
            f'IPSET={shlex.quote(transparent_proxy["ipset_path"])}',
            f'REDSOCKS_BIN={shlex.quote(transparent_proxy["redsocks_bin"])}',
            f'REDSOCKS_CONF={shlex.quote(str(resolve_local_path(transparent_proxy["redsocks_config_path"])))}',
            f'REDSOCKS_PID_FILE={shlex.quote(str(resolve_local_path(transparent_proxy["redsocks_pid_file"])))}',
            f'CHAIN={shlex.quote(transparent_proxy["chain_name"])}',
            f'DEST_NET_SET={shlex.quote(transparent_proxy["destination_subnet_set"])}',
            f'DEST_DOMAIN_SET={shlex.quote(transparent_proxy["destination_domain_set"])}',
            f'LISTEN_PORT={int(transparent_proxy["listen_port"])}',
            "",
            'stop_redsocks() {',
            '  if [ ! -f "$REDSOCKS_PID_FILE" ]; then',
            "    return 0",
            "  fi",
            '  PID="$(cat "$REDSOCKS_PID_FILE" 2>/dev/null || true)"',
            '  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then',
            '    kill "$PID" 2>/dev/null || true',
            "    COUNT=0",
            '    while [ "$COUNT" -lt 10 ] && kill -0 "$PID" 2>/dev/null; do',
            "      sleep 1",
            "      COUNT=$((COUNT + 1))",
            "    done",
            '    if kill -0 "$PID" 2>/dev/null; then',
            '      kill -9 "$PID" 2>/dev/null || true',
            "    fi",
            "  fi",
            '  rm -f "$REDSOCKS_PID_FILE"',
            "}",
            "",
            'stop_redsocks',
            '"$REDSOCKS_BIN" -c "$REDSOCKS_CONF" -p "$REDSOCKS_PID_FILE"',
            "sleep 1",
            'if [ ! -f "$REDSOCKS_PID_FILE" ]; then',
            '  echo "redsocks did not create pid file" >&2',
            "  exit 1",
            "fi",
            "",
            '"$IPSET" create "$DEST_NET_SET" hash:net family inet -exist',
            '"$IPSET" create "$DEST_DOMAIN_SET" hash:ip family inet -exist',
            '"$IPSET" flush "$DEST_NET_SET"',
            '"$IPSET" flush "$DEST_DOMAIN_SET"',
            *[
                f'"$IPSET" add "$DEST_NET_SET" {shlex.quote(subnet)} -exist'
                for subnet in destination_subnets
            ],
            "",
            '"$IPTABLES" -t nat -N "$CHAIN" 2>/dev/null || true',
            '"$IPTABLES" -t nat -F "$CHAIN"',
            "",
            *[
                f'"$IPTABLES" -t nat -A "$CHAIN" -d {shlex.quote(subnet)} -j RETURN'
                for subnet in bypass_subnets
            ],
            *(
                [
                    f'"$IPTABLES" -t nat -A "$CHAIN" -s {shlex.quote(subnet)} -p tcp -m set --match-set "$DEST_NET_SET" dst -j REDIRECT --to-ports "$LISTEN_PORT"'
                    for subnet in target_subnets
                ]
                if destination_subnets
                else []
            ),
            *(
                [
                    f'"$IPTABLES" -t nat -A "$CHAIN" -s {shlex.quote(subnet)} -p tcp -m set --match-set "$DEST_DOMAIN_SET" dst -j REDIRECT --to-ports "$LISTEN_PORT"'
                    for subnet in target_subnets
                ]
                if destination_domains
                else []
            ),
            *(
                []
                if selective_mode
                else [
                    f'"$IPTABLES" -t nat -A "$CHAIN" -s {shlex.quote(subnet)} -p tcp -j REDIRECT --to-ports "$LISTEN_PORT"'
                    for subnet in target_subnets
                ]
            ),
            '"$IPTABLES" -t nat -A "$CHAIN" -p tcp -j RETURN',
            "",
            'if ! "$IPTABLES" -t nat -C PREROUTING -p tcp -j "$CHAIN" 2>/dev/null; then',
            '  "$IPTABLES" -t nat -A PREROUTING -p tcp -j "$CHAIN"',
            "fi",
            "",
        ]
    )


def render_transparent_proxy_stop_script(config: dict[str, Any]) -> str:
    if transparent_proxy_uses_tun(config):
        return render_tun_policy_stop_script(config)

    transparent_proxy = config["transparent_proxy"]
    return "\n".join(
        [
            "#!/opt/bin/sh",
            "",
            "set -eu",
            "",
            f'IPTABLES={shlex.quote(transparent_proxy["iptables_path"])}',
            f'IPSET={shlex.quote(transparent_proxy["ipset_path"])}',
            f'REDSOCKS_PID_FILE={shlex.quote(str(resolve_local_path(transparent_proxy["redsocks_pid_file"])))}',
            f'CHAIN={shlex.quote(transparent_proxy["chain_name"])}',
            f'DEST_NET_SET={shlex.quote(transparent_proxy["destination_subnet_set"])}',
            f'DEST_DOMAIN_SET={shlex.quote(transparent_proxy["destination_domain_set"])}',
            "",
            'while "$IPTABLES" -t nat -C PREROUTING -p tcp -j "$CHAIN" 2>/dev/null; do',
            '  "$IPTABLES" -t nat -D PREROUTING -p tcp -j "$CHAIN"',
            "done",
            "",
            '"$IPTABLES" -t nat -F "$CHAIN" 2>/dev/null || true',
            '"$IPTABLES" -t nat -X "$CHAIN" 2>/dev/null || true',
            '"$IPSET" flush "$DEST_NET_SET" 2>/dev/null || true',
            '"$IPSET" destroy "$DEST_NET_SET" 2>/dev/null || true',
            '"$IPSET" flush "$DEST_DOMAIN_SET" 2>/dev/null || true',
            '"$IPSET" destroy "$DEST_DOMAIN_SET" 2>/dev/null || true',
            "",
            'if [ -f "$REDSOCKS_PID_FILE" ]; then',
            '  PID="$(cat "$REDSOCKS_PID_FILE" 2>/dev/null || true)"',
            '  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then',
            '    kill "$PID" 2>/dev/null || true',
            "    COUNT=0",
            '    while [ "$COUNT" -lt 10 ] && kill -0 "$PID" 2>/dev/null; do',
            "      sleep 1",
            "      COUNT=$((COUNT + 1))",
            "    done",
            '    if kill -0 "$PID" 2>/dev/null; then',
            '      kill -9 "$PID" 2>/dev/null || true',
            "    fi",
            "  fi",
            '  rm -f "$REDSOCKS_PID_FILE"',
            "fi",
            "",
        ]
    )


def generate_transparent_proxy_artifacts(
    config: dict[str, Any],
    vpn_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_runtime_dirs(config)
    transparent_proxy = config["transparent_proxy"]
    redsocks_conf_path = resolve_local_path(transparent_proxy["redsocks_config_path"])
    dnsmasq_ipset_config_path = resolve_local_path(transparent_proxy["dnsmasq_ipset_config_path"])
    rules_script_path = resolve_local_path(transparent_proxy["rules_script_path"])
    stop_script_path = resolve_local_path(transparent_proxy["stop_script_path"])
    dnsmasq_config_content = render_dnsmasq_ipset_config(config)
    dnsmasq_config_existed_before = dnsmasq_ipset_config_path.exists()
    dnsmasq_previous_content = ""
    if dnsmasq_config_existed_before:
        try:
            dnsmasq_previous_content = dnsmasq_ipset_config_path.read_text(encoding="utf-8")
        except OSError:
            dnsmasq_previous_content = ""

    upstream: dict[str, Any] | None = None
    if transparent_proxy_uses_redsocks(config):
        upstream = resolve_transparent_proxy_upstream(config, vpn_status)
        write_text_file(redsocks_conf_path, render_redsocks_config(config, upstream))
    else:
        try:
            if redsocks_conf_path.exists():
                redsocks_conf_path.unlink()
        except OSError:
            pass
    if dnsmasq_config_content:
        write_text_file(dnsmasq_ipset_config_path, dnsmasq_config_content)
    else:
        try:
            if dnsmasq_ipset_config_path.exists():
                dnsmasq_ipset_config_path.unlink()
        except OSError:
            pass
    write_text_file(rules_script_path, render_transparent_proxy_apply_script(config), executable=True)
    write_text_file(stop_script_path, render_transparent_proxy_stop_script(config), executable=True)
    payload = {
        "generated_at": utc_now(),
        "upstream": upstream,
        "redsocks_config": str(redsocks_conf_path),
        "mode": transparent_proxy["mode"],
        "dnsmasq_ipset_config": str(dnsmasq_ipset_config_path),
        "dnsmasq_ipset_config_exists": dnsmasq_ipset_config_path.exists(),
        "dnsmasq_ipset_config_existed_before": dnsmasq_config_existed_before,
        "dnsmasq_restart_required": dnsmasq_previous_content != dnsmasq_config_content,
        "apply_script": str(rules_script_path),
        "stop_script": str(stop_script_path),
        "selective_targets": {
            "destination_subnets": parse_csv_items(transparent_proxy.get("destination_subnets", "")),
            "destination_domains": parse_csv_items(transparent_proxy.get("destination_domains", "")),
            "enabled": has_selective_targets(config),
        },
    }
    append_debug_log(config, "transparent_proxy.artifacts.generated", payload=payload)
    return payload


def transparent_proxy_rule_installed(config: dict[str, Any]) -> bool:
    transparent_proxy = config["transparent_proxy"]
    if transparent_proxy_uses_tun(config):
        command = [
            transparent_proxy["iptables_path"],
            "-t",
            "mangle",
            "-C",
            "PREROUTING",
            "-j",
            transparent_proxy["chain_name"],
        ]
    else:
        command = [
            transparent_proxy["iptables_path"],
            "-t",
            "nat",
            "-C",
            "PREROUTING",
            "-p",
            "tcp",
            "-j",
            transparent_proxy["chain_name"],
        ]
    if not command_exists(command[0]):
        return False
    try:
        completed = subprocess.run(
            command,
            cwd=str(BASE_DIR),
            env=build_command_env(),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def get_transparent_proxy_status(
    config: dict[str, Any],
    vpn_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    transparent_proxy = config["transparent_proxy"]
    pid_path = resolve_local_path(transparent_proxy["redsocks_pid_file"])
    config_path = resolve_local_path(transparent_proxy["redsocks_config_path"])
    dnsmasq_ipset_config_path = resolve_local_path(transparent_proxy["dnsmasq_ipset_config_path"])
    apply_script = resolve_local_path(transparent_proxy["rules_script_path"])
    stop_script = resolve_local_path(transparent_proxy["stop_script_path"])

    pid: int | None = None
    running = False
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text(encoding="utf-8", errors="replace").strip())
            running = process_is_running(pid)
        except (OSError, ValueError):
            pid = None
            running = False

    upstream: dict[str, Any] | None = None
    upstream_error: str | None = None
    if transparent_proxy_uses_redsocks(config):
        try:
            upstream = resolve_transparent_proxy_upstream(config, vpn_status)
        except ValueError as exc:
            upstream_error = str(exc)

    status = {
        "mode": transparent_proxy["mode"],
        "enabled": bool(transparent_proxy["enabled"]),
        "available": (
            command_exists(transparent_proxy["redsocks_bin"])
            and command_exists(transparent_proxy["iptables_path"])
            and command_exists(transparent_proxy["ipset_path"])
        )
        if transparent_proxy_uses_redsocks(config)
        else (
            command_exists(transparent_proxy["ip_path"])
            and command_exists(transparent_proxy["iptables_path"])
            and command_exists(transparent_proxy["ipset_path"])
        ),
        "running": running,
        "pid": pid,
        "listener": (
            f"{transparent_proxy['listen_ip']}:{transparent_proxy['listen_port']}"
            if transparent_proxy_uses_redsocks(config)
            else None
        ),
        "chain_name": transparent_proxy["chain_name"],
        "target_subnets": parse_csv_items(transparent_proxy["target_subnets"]),
        "bypass_subnets": parse_csv_items(transparent_proxy["bypass_subnets"]),
        "destination_subnets": parse_csv_items(transparent_proxy.get("destination_subnets", "")),
        "destination_domains": parse_csv_items(transparent_proxy.get("destination_domains", "")),
        "destination_subnet_set": transparent_proxy["destination_subnet_set"],
        "destination_domain_set": transparent_proxy["destination_domain_set"],
        "selective_enabled": has_selective_targets(config),
        "rules_installed": transparent_proxy_rule_installed(config),
        "redsocks_config_path": str(config_path),
        "redsocks_config_exists": config_path.exists(),
        "dnsmasq_ipset_config_path": str(dnsmasq_ipset_config_path),
        "dnsmasq_ipset_config_exists": dnsmasq_ipset_config_path.exists(),
        "dnsmasq_restart_command": transparent_proxy.get("dnsmasq_restart_command", ""),
        "tun_interface": transparent_proxy.get("tun_interface"),
        "tun_route_table": transparent_proxy.get("tun_route_table"),
        "tun_fwmark": transparent_proxy.get("tun_fwmark"),
        "tun_rule_priority": transparent_proxy.get("tun_rule_priority"),
        "dns_hijack_enabled": bool(transparent_proxy.get("dns_hijack_enabled", False)),
        "dns_hijack_port": transparent_proxy.get("dns_hijack_port"),
        "apply_script_path": str(apply_script),
        "apply_script_exists": apply_script.exists(),
        "stop_script_path": str(stop_script),
        "stop_script_exists": stop_script.exists(),
        "upstream": upstream,
        "upstream_error": upstream_error,
        "vpn_connected": bool((vpn_status or {}).get("connected")),
        "vpn_listener": (vpn_status or {}).get("listener"),
        "vpn_mode": (vpn_status or {}).get("mode"),
    }
    with STATE_LOCK:
        STATE["last_transparent_proxy_status"] = status
    return status


def remember_transparent_proxy_action(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    with STATE_LOCK:
        STATE["last_transparent_proxy_action"] = payload
        STATE["last_transparent_proxy_status"] = payload.get("status")
    append_debug_log(config, "transparent_proxy.action.recorded", payload=payload)
    return payload


def maybe_restart_dnsmasq(
    config: dict[str, Any],
    *,
    artifacts: dict[str, Any] | None,
    event: str,
) -> dict[str, Any] | None:
    restart_required = bool((artifacts or {}).get("dnsmasq_restart_required"))
    if not restart_required:
        return None

    command_text = str(config["transparent_proxy"].get("dnsmasq_restart_command", "")).strip()
    if not command_text:
        return {
            "success": False,
            "skipped": True,
            "restart_required": True,
            "message": "Сгенерирован dnsmasq ipset-конфиг. Для применения нужен перезапуск dnsmasq через transparent_proxy.dnsmasq_restart_command.",
            "command": [],
            "executed_at": utc_now(),
        }

    result = run_shell_text_command(
        config,
        command_text,
        timeout=40,
        event=event,
    )
    result["restart_required"] = True
    return result


def stop_transparent_proxy(config: dict[str, Any], *, reason: str) -> dict[str, Any]:
    pid_path = resolve_local_path(config["transparent_proxy"]["redsocks_pid_file"])
    artifacts = generate_transparent_proxy_artifacts(config)
    if not command_exists(config["transparent_proxy"]["iptables_path"]) and not pid_path.exists():
        result = {
            "success": True,
            "message": "Transparent proxy уже выключен.",
            "executed_at": utc_now(),
            "stdout": "",
            "stderr": "",
            "returncode": 0,
            "command": [],
        }
    else:
        result = run_managed_command(
            config,
            [artifacts["stop_script"]],
            timeout=30,
            event="transparent_proxy.stop",
        )
    dnsmasq_result = maybe_restart_dnsmasq(
        config,
        artifacts=artifacts,
        event="transparent_proxy.dnsmasq_restart",
    )
    status = get_transparent_proxy_status(config)
    payload = {
        **result,
        "reason": reason,
        "artifacts": artifacts,
        "dnsmasq": dnsmasq_result,
        "status": status,
        "message": (
            "Transparent proxy остановлен."
            if result.get("success")
            else result.get("message", "Не удалось остановить transparent proxy.")
        ),
    }
    if dnsmasq_result and dnsmasq_result.get("skipped"):
        payload["message"] = (
            f"{payload['message']} {dnsmasq_result.get('message')}"
        ).strip()
        payload["success"] = False
    if dnsmasq_result and dnsmasq_result.get("success") is False and not dnsmasq_result.get("skipped"):
        payload["message"] = (
            f"{payload['message']} Перезапуск dnsmasq завершился с ошибкой."
        ).strip()
        payload["success"] = False
        if payload.get("returncode") in (0, None):
            payload["returncode"] = dnsmasq_result.get("returncode")
    return remember_transparent_proxy_action(config, payload)


def sync_transparent_proxy(
    config: dict[str, Any],
    *,
    vpn_status: dict[str, Any] | None = None,
    reason: str,
) -> dict[str, Any]:
    status = vpn_status or get_adguardvpn_status(config, persist_last_good=False)
    if not config["transparent_proxy"]["enabled"]:
        return stop_transparent_proxy(config, reason=f"{reason}:disabled")
    if not status.get("connected"):
        payload = stop_transparent_proxy(config, reason=f"{reason}:vpn-disconnected")
        payload["message"] = "VPN не подключён, transparent proxy снят."
        return remember_transparent_proxy_action(config, payload)
    if transparent_proxy_uses_tun(config) and "tun" not in str(status.get("mode") or "").lower():
        payload = {
            "success": False,
            "message": "VPN подключён не в TUN mode. Переподключите VPN после выбора tun-policy.",
            "executed_at": utc_now(),
            "stdout": "",
            "stderr": "Transport mismatch: expected TUN mode.",
            "returncode": 1,
            "command": [],
            "reason": reason,
            "vpn_status": status,
            "status": get_transparent_proxy_status(config, status),
        }
        return remember_transparent_proxy_action(config, payload)
    if transparent_proxy_uses_redsocks(config):
        try:
            upstream_check = resolve_transparent_proxy_upstream(config, status)
        except ValueError:
            upstream_check = None
        if not status.get("listener") or not upstream_check or not upstream_check.get("host"):
            payload = {
                "success": False,
                "message": "VPN подключён без SOCKS listener. Переподключите VPN после выбора transparent-redsocks.",
                "executed_at": utc_now(),
                "stdout": "",
                "stderr": "Transport mismatch: expected SOCKS listener.",
                "returncode": 1,
                "command": [],
                "reason": reason,
                "vpn_status": status,
                "status": get_transparent_proxy_status(config, status),
            }
            return remember_transparent_proxy_action(config, payload)

    artifacts = generate_transparent_proxy_artifacts(config, status)
    result = run_managed_command(
        config,
        [artifacts["apply_script"]],
        timeout=40,
        event="transparent_proxy.sync",
    )
    dnsmasq_result = maybe_restart_dnsmasq(
        config,
        artifacts=artifacts,
        event="transparent_proxy.dnsmasq_restart",
    )
    proxy_status = get_transparent_proxy_status(config, status)
    payload = {
        **result,
        "reason": reason,
        "artifacts": artifacts,
        "dnsmasq": dnsmasq_result,
        "vpn_status": status,
        "status": proxy_status,
        "message": (
            "Transparent proxy синхронизирован."
            if result.get("success")
            else result.get("message", "Не удалось синхронизировать transparent proxy.")
        ),
    }
    if dnsmasq_result and dnsmasq_result.get("skipped"):
        payload["message"] = (
            f"{payload['message']} {dnsmasq_result.get('message')}"
        ).strip()
        payload["success"] = False
    if dnsmasq_result and dnsmasq_result.get("success") is False and not dnsmasq_result.get("skipped"):
        payload["message"] = (
            f"{payload['message']} Перезапуск dnsmasq завершился с ошибкой."
        ).strip()
        payload["success"] = False
        if payload.get("returncode") in (0, None):
            payload["returncode"] = dnsmasq_result.get("returncode")
    return remember_transparent_proxy_action(config, payload)


def reconcile_transparent_proxy(
    config: dict[str, Any],
    *,
    vpn_status: dict[str, Any] | None = None,
    reason: str,
) -> dict[str, Any]:
    status = vpn_status or get_adguardvpn_status(config, persist_last_good=False)
    if config["transparent_proxy"]["enabled"] and status.get("connected"):
        return sync_transparent_proxy(config, vpn_status=status, reason=reason)
    return stop_transparent_proxy(config, reason=reason)


def execute_http_check(config: dict[str, Any], *, log_failures: bool = False) -> dict[str, Any]:
    vpn = config["vpn"]
    attempts: list[dict[str, Any]] = []
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    for attempt_index in range(1, vpn["check_retries"] + 1):
        started_at = time.time()
        append_debug_log(
            config,
            "http_check.attempt.started",
            attempt=attempt_index,
            url=vpn["test_url"],
            timeout=vpn["timeout"],
            connect_timeout=vpn["connect_timeout"],
        )
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
                    append_debug_log(config, "http_check.attempt.succeeded", result=attempt_result)
                    return {
                        "success": True,
                        "message": "Ресурс доступен и ожидаемый текст найден.",
                        "attempts": attempts,
                        "checked_at": utc_now(),
                    }

                if status_code not in (200, 301, 302):
                    attempt_result["message"] = f"HTTP error: {status_code}"
                    if log_failures:
                        append_rotation_log(config, f"HTTP check failed: url={vpn['test_url']} code={status_code}")
                else:
                    attempt_result["message"] = "Ответ получен, но проверка текста не пройдена."
                    if log_failures:
                        append_rotation_log(
                            config,
                            f"Content check failed: expected text not found for {vpn['test_url']}",
                        )
                append_debug_log(config, "http_check.attempt.failed", result=attempt_result)
        except urllib.error.HTTPError as exc:
            attempt_result.update(
                {
                    "status_code": exc.code,
                    "message": f"HTTP error: {exc.code}",
                    "duration_ms": round((time.time() - started_at) * 1000, 2),
                }
            )
            if log_failures:
                append_rotation_log(config, f"HTTP check failed: url={vpn['test_url']} code={exc.code}")
            append_debug_log(config, "http_check.attempt.http_error", result=attempt_result)
        except Exception as exc:  # noqa: BLE001
            attempt_result.update(
                {
                    "status_code": 0,
                    "message": str(exc),
                    "duration_ms": round((time.time() - started_at) * 1000, 2),
                }
            )
            if log_failures:
                append_rotation_log(config, f"HTTP check failed: url={vpn['test_url']} code=000 error={exc}")
            append_debug_log(config, "http_check.attempt.exception", result=attempt_result)

        attempts.append(attempt_result)
        if attempt_index < vpn["check_retries"]:
            time.sleep(vpn["check_retry_delay"])

    return {
        "success": False,
        "message": "Ресурс недоступен или страница не содержит ожидаемый текст.",
        "attempts": attempts,
        "checked_at": utc_now(),
    }


def perform_http_check(config: dict[str, Any]) -> dict[str, Any]:
    result = execute_http_check(config, log_failures=False)
    update_last_check_state(result)
    return result


def get_rotation_candidates(config: dict[str, Any]) -> dict[str, Any]:
    limit = config["vpn"]["top_count"]
    payload = get_adguardvpn_locations(config, limit=limit)
    candidates: list[str] = []
    seen: set[str] = set()
    for item in payload.get("items", []):
        location = normalize_location_name(item.get("city") or item.get("code"))
        normalized = location.casefold()
        if location and normalized not in seen:
            candidates.append(location)
            seen.add(normalized)

    result = {
        "payload": payload,
        "candidates": candidates,
    }
    append_debug_log(
        config,
        "rotation.candidates.loaded",
        candidate_count=len(candidates),
        candidates=candidates,
        payload={
            "success": payload.get("success"),
            "message": payload.get("message"),
            "returncode": payload.get("returncode"),
        },
    )
    return result


def try_rotation_location(
    config: dict[str, Any],
    location: str,
    output_lines: list[str],
) -> dict[str, Any]:
    current_status = get_adguardvpn_status(config, persist_last_good=False)
    current_location = current_status.get("location")
    step: dict[str, Any] = {
        "location": location,
        "current_location": current_location,
        "switched": False,
    }

    if same_location(current_location, location):
        message = f"Skipping location {location} because it is already current"
        append_rotation_log(config, message)
        output_lines.append(message)
    else:
        message = f"Trying location: {location}"
        append_rotation_log(config, message)
        output_lines.append(message)
        step["disconnect"] = disconnect_adguardvpn(config)
        time.sleep(3)
        step["connect"] = connect_adguardvpn(config, location)
        step["switched"] = True
        time.sleep(config["vpn"]["switch_delay"])
    append_debug_log(config, "rotation.location.status_before_check", step=step)

    status_after = get_adguardvpn_status(config, persist_last_good=False)
    step["status"] = status_after
    check_result = execute_http_check(config, log_failures=True)
    update_last_check_state(check_result)
    step["check"] = check_result

    if check_result.get("success"):
        final_location = status_after.get("location") or location
        write_last_good_location(config, final_location)
        success_message = f"SUCCESS: resource reachable via {final_location}"
        append_rotation_log(config, success_message)
        output_lines.append(success_message)
        step["success"] = True
        step["final_location"] = final_location
        append_debug_log(config, "rotation.location.succeeded", step=step)
        return step

    failure_message = f"FAILED: resource unreachable via {location}"
    append_rotation_log(config, failure_message)
    output_lines.append(failure_message)
    step["success"] = False
    append_debug_log(config, "rotation.location.failed", step=step)
    return step


def try_rotation_quick_connect(config: dict[str, Any], output_lines: list[str]) -> dict[str, Any]:
    append_rotation_log(config, "Fallback: trying quick connect")
    output_lines.append("Fallback: trying quick connect")
    step: dict[str, Any] = {
        "location": None,
        "disconnect": disconnect_adguardvpn(config),
    }
    time.sleep(3)
    step["connect"] = connect_adguardvpn(config)
    time.sleep(config["vpn"]["switch_delay"])
    append_debug_log(config, "rotation.quick_connect.command_result", step=step)

    status_after = get_adguardvpn_status(config, persist_last_good=False)
    step["status"] = status_after
    check_result = execute_http_check(config, log_failures=True)
    update_last_check_state(check_result)
    step["check"] = check_result

    if check_result.get("success"):
        final_location = status_after.get("location")
        write_last_good_location(config, final_location)
        success_message = f"SUCCESS: resource reachable via {final_location or 'quick connect'}"
        append_rotation_log(config, success_message)
        output_lines.append(success_message)
        step["success"] = True
        step["final_location"] = final_location
        append_debug_log(config, "rotation.quick_connect.succeeded", step=step)
        return step

    append_rotation_log(config, "ERROR: no working location found")
    output_lines.append("ERROR: no working location found")
    step["success"] = False
    append_debug_log(config, "rotation.quick_connect.failed", step=step)
    return step


def run_rotation(
    config: dict[str, Any],
    *,
    trigger: str = "manual",
    wait_for_lock: bool = True,
) -> dict[str, Any]:
    action_lock_acquired = ACTION_LOCK.acquire(blocking=wait_for_lock)
    if not action_lock_acquired:
        result = {
            "success": True,
            "message": "Другая проверка или ротация уже выполняется, автоматический запуск пропущен.",
            "executed_at": utc_now(),
            "stdout": "",
            "stderr": "",
            "returncode": 0,
            "command": [],
            "generated_script": None,
            "skipped": True,
            "trigger": trigger,
            "runner": "python-native",
        }
        append_debug_log(config, "rotation.action_lock.busy", result=result)
        return result

    try:
        generation = generate_script(config)
        command = [config["autostart"]["python_bin"], "vpn_panel_server.py", "rotate"]
        append_debug_log(
            config,
            "rotation.started",
            command=command,
            trigger=trigger,
            test_url=config["vpn"]["test_url"],
            top_count=config["vpn"]["top_count"],
        )
        acquired, active_pid = acquire_rotation_file_lock(config)
        if not acquired:
            message = (
                f"Переключение уже выполняется (PID {active_pid})."
                if active_pid
                else "Не удалось установить lock-файл для переключения."
            )
            result = {
                "success": bool(active_pid),
                "message": message,
                "executed_at": utc_now(),
                "stdout": "",
                "stderr": "" if active_pid else message,
                "returncode": 0 if active_pid else 1,
                "command": command,
                "generated_script": generation,
                "skipped": bool(active_pid),
                "trigger": trigger,
                "runner": "python-native",
            }
            with STATE_LOCK:
                STATE["last_rotation"] = result
            append_debug_log(config, "rotation.skipped", result=result)
            return result

        output_lines: list[str] = []
        attempts: list[dict[str, Any]] = []
        try:
            initial_check = execute_http_check(config, log_failures=True)
            update_last_check_state(initial_check)
            append_debug_log(config, "rotation.initial_check", result=initial_check)
            if initial_check.get("success"):
                append_rotation_log(config, "OK: resource reachable, no switch needed")
                output_lines.append("OK: resource reachable, no switch needed")
                result = {
                    "success": True,
                    "message": "Ресурс уже доступен, переключение не потребовалось.",
                    "executed_at": utc_now(),
                    "stdout": "\n".join(output_lines),
                    "stderr": "",
                    "returncode": 0,
                    "command": command,
                    "generated_script": generation,
                    "initial_check": initial_check,
                    "attempts": attempts,
                    "trigger": trigger,
                    "runner": "python-native",
                }
                with STATE_LOCK:
                    STATE["last_rotation"] = result
                append_debug_log(config, "rotation.completed", result=result)
                return result

            append_rotation_log(config, "FAIL: resource unreachable, starting location rotation")
            output_lines.append("FAIL: resource unreachable, starting location rotation")

            last_good = read_last_good_location(config)
            append_debug_log(config, "rotation.last_good_location", last_good=last_good)
            if last_good:
                append_rotation_log(config, f"Trying last known good location: {last_good}")
                output_lines.append(f"Trying last known good location: {last_good}")
                attempt = try_rotation_location(config, last_good, output_lines)
                attempts.append(attempt)
                if attempt.get("success"):
                    result = {
                        "success": True,
                        "message": f"Ресурс восстановлен через {attempt.get('final_location') or last_good}.",
                        "executed_at": utc_now(),
                        "stdout": "\n".join(output_lines),
                        "stderr": "",
                        "returncode": 0,
                        "command": command,
                        "generated_script": generation,
                        "initial_check": initial_check,
                        "attempts": attempts,
                        "trigger": trigger,
                        "runner": "python-native",
                    }
                    with STATE_LOCK:
                        STATE["last_rotation"] = result
                    append_debug_log(config, "rotation.completed", result=result)
                    return result

            locations_data = get_rotation_candidates(config)
            candidate_locations = locations_data["candidates"]
            if not candidate_locations:
                append_rotation_log(config, "ERROR: could not get locations list")
                output_lines.append("ERROR: could not get locations list")
                quick_connect = try_rotation_quick_connect(config, output_lines)
                attempts.append(quick_connect)
                final_success = bool(quick_connect.get("success"))
                result = {
                    "success": final_success,
                    "message": (
                        f"Список локаций не получен, но quick connect восстановил доступ через {quick_connect.get('final_location') or 'текущую локацию'}."
                        if final_success
                        else "Не удалось получить список локаций и quick connect тоже не помог."
                    ),
                    "executed_at": utc_now(),
                    "stdout": "\n".join(output_lines),
                    "stderr": "",
                    "returncode": 0 if final_success else 1,
                    "command": command,
                    "generated_script": generation,
                    "initial_check": initial_check,
                    "attempts": attempts,
                    "locations": locations_data["payload"],
                    "trigger": trigger,
                    "runner": "python-native",
                }
                with STATE_LOCK:
                    STATE["last_rotation"] = result
                append_debug_log(config, "rotation.completed", result=result)
                return result

            for location in candidate_locations:
                if same_location(location, last_good):
                    continue
                attempt = try_rotation_location(config, location, output_lines)
                attempts.append(attempt)
                if attempt.get("success"):
                    result = {
                        "success": True,
                        "message": f"Ресурс восстановлен через {attempt.get('final_location') or location}.",
                        "executed_at": utc_now(),
                        "stdout": "\n".join(output_lines),
                        "stderr": "",
                        "returncode": 0,
                        "command": command,
                        "generated_script": generation,
                        "initial_check": initial_check,
                        "attempts": attempts,
                        "locations": locations_data["payload"],
                        "trigger": trigger,
                        "runner": "python-native",
                    }
                    with STATE_LOCK:
                        STATE["last_rotation"] = result
                    append_debug_log(config, "rotation.completed", result=result)
                    return result

            quick_connect = try_rotation_quick_connect(config, output_lines)
            attempts.append(quick_connect)
            final_success = bool(quick_connect.get("success"))
            message = (
                f"Ресурс восстановлен через {quick_connect.get('final_location') or 'quick connect'}."
                if final_success
                else "Не удалось подобрать рабочую локацию."
            )
            result = {
                "success": final_success,
                "message": message,
                "executed_at": utc_now(),
                "stdout": "\n".join(output_lines),
                "stderr": "",
                "returncode": 0 if final_success else 1,
                "command": command,
                "generated_script": generation,
                "initial_check": initial_check,
                "attempts": attempts,
                "locations": locations_data["payload"],
                "trigger": trigger,
                "runner": "python-native",
            }
        except Exception as exc:  # noqa: BLE001
            result = {
                "success": False,
                "message": str(exc),
                "executed_at": utc_now(),
                "stdout": "\n".join(output_lines),
                "stderr": str(exc),
                "returncode": 1,
                "command": command,
                "generated_script": generation,
                "attempts": attempts,
                "trigger": trigger,
                "runner": "python-native",
            }
            append_rotation_log(config, f"ERROR: rotation crashed: {exc}")
            append_debug_log(config, "rotation.crashed", error=str(exc), attempts=attempts)
        finally:
            release_rotation_file_lock(config)

        with STATE_LOCK:
            STATE["last_rotation"] = result
        append_debug_log(config, "rotation.completed", result=result)
        return result
    finally:
        ACTION_LOCK.release()


def update_automation_config(
    config: dict[str, Any],
    *,
    enabled: bool | None = None,
    check_interval: int | None = None,
) -> dict[str, Any]:
    updated = deep_copy(config)
    if enabled is not None:
        updated["automation"]["enabled"] = bool(enabled)
    if check_interval is not None:
        updated["automation"]["check_interval"] = int(check_interval)
    validated = validate_config(updated)
    write_config(validated)
    notify_automation_config_changed()
    return {
        "success": True,
        "message": "Настройки автоматического режима обновлены.",
        "config": validated,
        "automation": get_automation_status(validated),
        "updated_at": utc_now(),
    }


def run_automation_cycle(config: dict[str, Any]) -> dict[str, Any]:
    started_at = utc_now()
    interval = int(config["automation"]["check_interval"])
    update_automation_runtime(
        loop_running=True,
        last_started_at=started_at,
        next_check_at=None,
        last_error=None,
        current_interval=interval,
    )
    result = run_rotation(config, trigger="automatic", wait_for_lock=False)
    completed_at = utc_now()
    payload = {
        "success": bool(result.get("success")),
        "message": result.get("message", ""),
        "executed_at": result.get("executed_at") or completed_at,
        "completed_at": completed_at,
        "trigger": "automatic",
        "skipped": bool(result.get("skipped")),
        "returncode": result.get("returncode"),
    }
    with STATE_LOCK:
        STATE["last_automation_action"] = payload

    runtime_result = {
        "success": payload["success"],
        "message": payload["message"],
        "skipped": payload["skipped"],
        "executed_at": payload["executed_at"],
    }
    update_automation_runtime(
        loop_running=False,
        last_completed_at=completed_at,
        last_error=None if payload["success"] else payload["message"],
        last_result=runtime_result,
    )
    append_debug_log(config, "automation.cycle.completed", result=payload)
    return payload


def automation_loop(stop_event: threading.Event) -> None:
    update_automation_runtime(
        thread_alive=True,
        thread_started_at=utc_now(),
        loop_running=False,
        last_error=None,
    )
    config_signature: tuple[bool, int] | None = None
    next_run_monotonic: float | None = None

    while not stop_event.is_set():
        try:
            config = load_config()
            ensure_runtime_dirs(config)
            automation_cfg = config["automation"]
            enabled = bool(automation_cfg["enabled"])
            interval = int(automation_cfg["check_interval"])
            signature = (enabled, interval)
            now_monotonic = time.monotonic()

            if signature != config_signature:
                config_signature = signature
                next_run_monotonic = now_monotonic if enabled else None

            if not enabled:
                update_automation_runtime(
                    loop_running=False,
                    next_check_at=None,
                    current_interval=interval,
                )
                AUTOMATION_WAKE_EVENT.wait(timeout=1)
                AUTOMATION_WAKE_EVENT.clear()
                continue

            if next_run_monotonic is None:
                next_run_monotonic = now_monotonic

            wait_seconds = max(0.0, next_run_monotonic - now_monotonic)
            update_automation_runtime(
                loop_running=False,
                current_interval=interval,
                next_check_at=utc_from_timestamp(time.time() + wait_seconds),
            )

            if wait_seconds > 0:
                AUTOMATION_WAKE_EVENT.wait(timeout=min(1.0, wait_seconds))
                AUTOMATION_WAKE_EVENT.clear()
                continue

            run_automation_cycle(config)
            next_run_monotonic = time.monotonic() + interval
            update_automation_runtime(next_check_at=utc_from_timestamp(time.time() + interval))
        except Exception as exc:  # noqa: BLE001
            update_automation_runtime(
                loop_running=False,
                last_completed_at=utc_now(),
                last_error=str(exc),
                next_check_at=utc_from_timestamp(time.time() + 5),
            )
            AUTOMATION_WAKE_EVENT.wait(timeout=5)
            AUTOMATION_WAKE_EVENT.clear()

    update_automation_runtime(
        thread_alive=False,
        loop_running=False,
        next_check_at=None,
    )


def start_automation_worker() -> tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    worker = threading.Thread(
        target=automation_loop,
        args=(stop_event,),
        name="vpn-automation",
        daemon=True,
    )
    worker.start()
    return worker, stop_event


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
    append_debug_log(config, "cli.command.started", command=command, timeout=timeout or config["adguardvpn"]["command_timeout"])
    try:
        with VPN_COMMAND_LOCK:
            completed = subprocess.run(
                command,
                cwd=str(BASE_DIR),
                env=build_command_env(),
                capture_output=True,
                text=True,
                timeout=timeout or config["adguardvpn"]["command_timeout"],
                check=False,
            )
        result = {
            "success": completed.returncode == 0,
            "available": True,
            "message": "Команда выполнена." if completed.returncode == 0 else "Команда завершилась с ошибкой.",
            "executed_at": utc_now(),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
            "command": command,
        }
        append_debug_log(config, "cli.command.completed", result=result)
        return result
    except subprocess.TimeoutExpired as exc:
        result = {
            "success": False,
            "available": True,
            "message": "Команда adguardvpn-cli превысила таймаут.",
            "executed_at": utc_now(),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "returncode": None,
            "command": command,
        }
        append_debug_log(config, "cli.command.timeout", result=result)
        return result


def parse_adguardvpn_status(result: dict[str, Any]) -> dict[str, Any]:
    command_success = result.get("success", False)
    status = {
        "available": result.get("available", False),
        "success": command_success,
        "command_success": command_success,
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

    text = result.get("stdout", "").replace("\r", "")
    clean_text = strip_ansi(text)
    if not clean_text.strip():
        return status

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
    lowered_text = clean_text.lower()
    disconnected_markers = (
        "not connected",
        "disconnected",
        "failed to disconnect",
        "process is not running",
    )
    has_disconnect_marker = any(marker in lowered_text for marker in disconnected_markers)
    connected = bool(location) or (
        "connected" in lowered_text and "not connected" not in lowered_text
    )
    if state_value:
        connected = "connected" in state_value and "not connected" not in state_value
    if has_disconnect_marker:
        connected = False

    parsed_success = bool(clean_text.strip())
    status.update(
        {
            "success": command_success or parsed_success,
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
    if not command_success and status["message"] == "Команда завершилась с ошибкой.":
        status["message"] = "Команда вернула ненулевой код, но статус был прочитан."
    return status


def parse_adguardvpn_locations(result: dict[str, Any]) -> dict[str, Any]:
    command_success = result.get("success", False)
    payload = {
        "available": result.get("available", False),
        "success": command_success,
        "command_success": command_success,
        "message": result.get("message", ""),
        "executed_at": result.get("executed_at"),
        "items": [],
        "raw": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "returncode": result.get("returncode"),
        "command": result.get("command", []),
    }

    raw_text = result.get("stdout", "").replace("\r", "")
    clean_raw = strip_ansi(raw_text)
    if not clean_raw.strip():
        return payload

    lines = clean_raw.splitlines()
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
    if items:
        payload["success"] = True
        payload["message"] = f"Найдено локаций: {len(items)}"
    elif not command_success and payload["message"] == "Команда завершилась с ошибкой.":
        payload["message"] = "Команда вернула ненулевой код, список локаций не распознан."
    payload["clean_raw"] = "\n".join(lines)
    return payload


def get_adguardvpn_status(config: dict[str, Any], *, persist_last_good: bool = True) -> dict[str, Any]:
    result = parse_adguardvpn_status(run_adguardvpn_cli(config, ["status"]))
    if persist_last_good and result.get("connected") and result.get("location"):
        write_last_good_location(config, result["location"])
    with STATE_LOCK:
        STATE["last_vpn_status"] = result
    return result


def get_adguardvpn_locations(config: dict[str, Any], limit: int | None = None) -> dict[str, Any]:
    safe_limit = limit or config["adguardvpn"]["locations_limit"]
    result = parse_adguardvpn_locations(run_adguardvpn_cli(config, ["list-locations"]))
    result["items"] = result.get("items", [])[:safe_limit]
    if result.get("items"):
        result["message"] = f"Найдено локаций: {len(result['items'])}"
    with STATE_LOCK:
        STATE["last_vpn_locations"] = result
    return result


def connect_adguardvpn(config: dict[str, Any], location: str | None = None) -> dict[str, Any]:
    args = ["connect"]
    if location:
        args.extend(["-l", location])
    transport = prepare_adguardvpn_transport(config)
    if not transport.get("success"):
        payload = {
            "success": False,
            "available": True,
            "message": transport.get("message", "Не удалось подготовить transport mode."),
            "executed_at": utc_now(),
            "stdout": "",
            "stderr": transport.get("message", ""),
            "returncode": 1,
            "command": [],
            "location": location,
            "transport": transport,
            "status": get_adguardvpn_status(config, persist_last_good=False),
            "transparent_proxy": get_transparent_proxy_status(config),
        }
        with STATE_LOCK:
            STATE["last_cli_action"] = payload
        return payload
    result = run_adguardvpn_cli(config, args)
    status = get_adguardvpn_status(config)
    if status.get("connected") and status.get("location"):
        write_last_good_location(config, status["location"])
    transparent_proxy = reconcile_transparent_proxy(config, vpn_status=status, reason="connect")
    payload = {
        **result,
        "location": location,
        "transport": transport,
        "status": status,
        "transparent_proxy": transparent_proxy,
    }
    with STATE_LOCK:
        STATE["last_cli_action"] = payload
    return payload


def disconnect_adguardvpn(config: dict[str, Any]) -> dict[str, Any]:
    result = run_adguardvpn_cli(config, ["disconnect"])
    status = get_adguardvpn_status(config)
    transparent_proxy = reconcile_transparent_proxy(config, vpn_status=status, reason="disconnect")
    payload = {
        **result,
        "status": status,
        "transparent_proxy": transparent_proxy,
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
            "export SSL_CERT_FILE=/opt/etc/ssl/certs/ca-certificates.crt",
            "export HOME=/opt/home/admin",
            "PATH=/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin",
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
            f'LOG_FILE={shlex.quote(autostart["log_file"])}',
            "",
            "start() {",
            '  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then',
            '    echo "$NAME already running"',
            "    return 0",
            "  fi",
            "",
            "  mkdir -p /opt/var/run",
            '  "$START_SCRIPT" &',
            "  PID=$!",
            '  echo "$PID" > "$PID_FILE"',
            "  sleep 2",
            '  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then',
            '    echo "$NAME started"',
            "    return 0",
            "  fi",
            "",
            '  echo "$NAME failed to start"',
            '  rm -f "$PID_FILE"',
            '  if [ -f "$LOG_FILE" ]; then',
            '    tail -n 40 "$LOG_FILE"',
            "  fi",
            "  return 1",
            "}",
            "",
            "stop_wait() {",
            '  PID="$1"',
            "  COUNT=0",
            '  while [ "$COUNT" -lt 10 ]; do',
            '    if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then',
            "      return 0",
            "    fi",
            "    sleep 1",
            "    COUNT=$((COUNT + 1))",
            "  done",
            "  return 1",
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
            '    if ! stop_wait "$PID"; then',
            '      echo "$NAME did not stop in time"',
            "      return 1",
            "    fi",
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


def build_restart_helper_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        creationflags = 0
        for name in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS"):
            creationflags |= int(getattr(subprocess, name, 0))
        return {"creationflags": creationflags}
    return {"start_new_session": True}


def schedule_service_restart(config: dict[str, Any], delay_seconds: int) -> dict[str, Any]:
    init_script = Path(config["autostart"]["init_script_path"])
    log_file = Path(config["autostart"]["log_file"])
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    helper_code = (
        "import subprocess, sys, time; "
        "time.sleep(float(sys.argv[1])); "
        "log_path=sys.argv[2]; "
        "command=sys.argv[3:]; "
        "handle=None; "
        "stdout=stderr=None; "
        "try:\n"
        " handle=open(log_path,'a',encoding='utf-8')\n"
        " stdout=stderr=handle\n"
        "except OSError:\n"
        " handle=None\n"
        "kwargs={}; "
        "kwargs['start_new_session']=True if sys.platform != 'win32' else False; "
        "if sys.platform == 'win32':\n"
        " kwargs['creationflags']=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)|getattr(subprocess,'DETACHED_PROCESS',0)\n"
        "subprocess.Popen(command, stdout=stdout, stderr=stderr, **kwargs)"
    )
    helper_command = [
        sys.executable,
        "-c",
        helper_code,
        str(delay_seconds),
        str(log_file),
        str(init_script),
        "restart",
    ]
    subprocess.Popen(helper_command, cwd=str(BASE_DIR), **build_restart_helper_kwargs())
    return {
        "scheduled": True,
        "method": "init-script",
        "delay_seconds": delay_seconds,
        "command": [str(init_script), "restart"],
    }


def schedule_process_restart(config: dict[str, Any], delay_seconds: int) -> dict[str, Any]:
    log_file = Path(config["autostart"]["log_file"])
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    script_path = str((BASE_DIR / "vpn_panel_server.py").resolve())
    restart_command = [sys.executable, script_path]
    helper_code = (
        "import os, signal, subprocess, sys, time; "
        "delay=float(sys.argv[1]); "
        "pid=int(sys.argv[2]); "
        "cwd=sys.argv[3]; "
        "log_path=sys.argv[4]; "
        "command=sys.argv[5:]; "
        "time.sleep(delay); "
        "try:\n"
        " os.kill(pid, getattr(signal,'SIGTERM',15))\n"
        "except OSError:\n"
        " pass\n"
        "time.sleep(1.0); "
        "handle=None; "
        "stdout=stderr=None; "
        "try:\n"
        " handle=open(log_path,'a',encoding='utf-8')\n"
        " stdout=stderr=handle\n"
        "except OSError:\n"
        " handle=None\n"
        "kwargs={'cwd': cwd}; "
        "kwargs['start_new_session']=True if sys.platform != 'win32' else False; "
        "if sys.platform == 'win32':\n"
        " kwargs['creationflags']=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)|getattr(subprocess,'DETACHED_PROCESS',0)\n"
        "subprocess.Popen(command, stdout=stdout, stderr=stderr, **kwargs)"
    )
    helper_command = [
        sys.executable,
        "-c",
        helper_code,
        str(delay_seconds),
        str(os.getpid()),
        str(BASE_DIR),
        str(log_file),
        *restart_command,
    ]
    subprocess.Popen(helper_command, cwd=str(BASE_DIR), **build_restart_helper_kwargs())
    return {
        "scheduled": True,
        "method": "process-reexec",
        "delay_seconds": delay_seconds,
        "command": restart_command,
    }


def schedule_panel_restart_after_update(config: dict[str, Any], delay_seconds: int = 2) -> dict[str, Any]:
    autostart_status = get_autostart_status(config)
    init_script = Path(config["autostart"]["init_script_path"])
    if (
        init_script.exists()
        and autostart_status.get("running")
        and autostart_status.get("pid") == os.getpid()
    ):
        return schedule_service_restart(config, delay_seconds)
    return schedule_process_restart(config, delay_seconds)


def restart_panel(config: dict[str, Any], delay_seconds: int = 2) -> dict[str, Any]:
    with ACTION_LOCK:
        append_debug_log(config, "panel_restart.requested", delay_seconds=delay_seconds)
        restart_info = schedule_panel_restart_after_update(config, delay_seconds)
        result = {
            "success": bool(restart_info.get("scheduled")),
            "message": (
                f"Перезапуск панели запланирован через {restart_info.get('delay_seconds', delay_seconds)} сек."
                if restart_info.get("scheduled")
                else "Не удалось запланировать перезапуск панели."
            ),
            "executed_at": utc_now(),
            "restart_scheduled": bool(restart_info.get("scheduled")),
            "restart_method": restart_info.get("method"),
            "restart_delay_seconds": restart_info.get("delay_seconds"),
            "restart_command": restart_info.get("command"),
        }
        append_debug_log(config, "panel_restart.scheduled", restart=restart_info, result=result)
        return result


def run_project_update(config: dict[str, Any]) -> dict[str, Any]:
    with ACTION_LOCK:
        update_script = (BASE_DIR / "install" / "update.sh").resolve()
        command = [str(update_script)]

        if not update_script.exists():
            result = {
                "success": False,
                "message": "Скрипт обновления не найден.",
                "executed_at": utc_now(),
                "stdout": "",
                "stderr": "",
                "returncode": None,
                "command": command,
                "restart_scheduled": False,
            }
            with STATE_LOCK:
                STATE["last_update_action"] = result
            return result

        try:
            update_script.chmod(update_script.stat().st_mode | 0o111)
        except OSError:
            pass

        append_debug_log(config, "project_update.started", command=command)
        try:
            completed = subprocess.run(
                command,
                cwd=str(BASE_DIR),
                env=build_command_env(),
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
            result = {
                "success": completed.returncode == 0,
                "message": "Обновление завершено." if completed.returncode == 0 else "Обновление завершилось с ошибкой.",
                "executed_at": utc_now(),
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "returncode": completed.returncode,
                "command": command,
                "restart_scheduled": False,
            }
            if result["success"]:
                try:
                    restart_info = schedule_panel_restart_after_update(config)
                    result["restart_scheduled"] = bool(restart_info.get("scheduled"))
                    result["restart_method"] = restart_info.get("method")
                    result["restart_delay_seconds"] = restart_info.get("delay_seconds")
                    result["restart_command"] = restart_info.get("command")
                    if result["restart_scheduled"]:
                        result["message"] = (
                            f"Обновление завершено. Перезапуск панели запланирован через "
                            f"{result['restart_delay_seconds']} сек."
                        )
                        append_debug_log(config, "project_update.restart_scheduled", restart=restart_info)
                except Exception as restart_exc:  # noqa: BLE001
                    result["restart_error"] = str(restart_exc)
                    append_debug_log(config, "project_update.restart_failed", error=str(restart_exc))
        except subprocess.TimeoutExpired as exc:
            result = {
                "success": False,
                "message": "Скрипт обновления превысил таймаут.",
                "executed_at": utc_now(),
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "returncode": None,
                "command": command,
                "restart_scheduled": False,
            }

        with STATE_LOCK:
            STATE["last_update_action"] = result
        append_debug_log(config, "project_update.completed", result=result)
        return result


def clear_logs(config: dict[str, Any]) -> dict[str, Any]:
    log_paths = [
        Path(config["paths"]["log_file"]),
        Path(config["logging"]["debug_log_file"]),
    ]
    cleared: list[str] = []
    missing: list[str] = []
    removed_rotations: list[str] = []

    for path in log_paths:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        if path.exists():
            try:
                path.write_text("", encoding="utf-8")
                cleared.append(str(path))
            except OSError:
                missing.append(str(path))
        else:
            missing.append(str(path))

        for rotated in sorted(path.parent.glob(f"{path.name}.*")):
            try:
                rotated.unlink()
                removed_rotations.append(str(rotated))
            except OSError:
                continue

    result = {
        "success": True,
        "message": "Логи очищены.",
        "executed_at": utc_now(),
        "cleared": cleared,
        "missing": missing,
        "removed_rotations": removed_rotations,
    }
    with STATE_LOCK:
        STATE["last_check"] = None
    return result


def collect_state(config: dict[str, Any]) -> dict[str, Any]:
    generated_path = resolve_local_path(config["panel"]["generated_script"])
    source_path = resolve_local_path(config["panel"]["source_script"])
    log_path = Path(config["paths"]["log_file"])
    debug_log_path = Path(config["logging"]["debug_log_file"])

    with STATE_LOCK:
        snapshot = deep_copy(STATE)

    last_good_location = read_last_good_location(config)
    if not last_good_location:
        last_status = snapshot.get("last_vpn_status") or {}
        last_good_location = last_status.get("location")

    transparent_proxy_status = get_transparent_proxy_status(
        config,
        snapshot.get("last_vpn_status"),
    )

    return {
        "config_path": str(CONFIG_PATH),
        "panel_url": f"http://{get_panel_access_host(config)}:{config['panel']['port']}",
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
        "debug_log_file": {
            "path": str(debug_log_path),
            "exists": debug_log_path.exists(),
            "size": debug_log_path.stat().st_size if debug_log_path.exists() else 0,
            "enabled": bool(config["logging"]["debug_enabled"]),
        },
        "logging": {
            "debug_enabled": bool(config["logging"]["debug_enabled"]),
            "debug_max_bytes": config["logging"]["debug_max_bytes"],
            "debug_backup_count": config["logging"]["debug_backup_count"],
        },
        "transparent_proxy": transparent_proxy_status,
        "automation": get_automation_status(config),
        "resource_count": len(config.get("resources", {}).get("links", [])),
        "last_good_location": last_good_location,
        "last_check": snapshot.get("last_check"),
        "last_rotation": snapshot.get("last_rotation"),
        "last_automation_action": snapshot.get("last_automation_action"),
        "last_script_generation": snapshot.get("last_script_generation"),
        "last_cli_action": snapshot.get("last_cli_action"),
        "last_vpn_status": snapshot.get("last_vpn_status"),
        "last_transparent_proxy_action": snapshot.get("last_transparent_proxy_action"),
        "last_autostart_action": snapshot.get("last_autostart_action"),
        "last_update_action": snapshot.get("last_update_action"),
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
            if self.path == "/assets/logo.ico":
                return self.serve_asset("logo.ico", "image/x-icon")
            if self.path == "/api/config":
                return self.send_json(load_config())
            if self.path == "/api/state":
                return self.send_json(collect_state(load_config()))
            if self.path == "/api/adguardvpn/status":
                return self.send_json(get_adguardvpn_status(load_config()))
            if self.path == "/api/adguardvpn/locations":
                return self.send_json(get_adguardvpn_locations(load_config()))
            if self.path == "/api/transparent-proxy/status":
                config = load_config()
                vpn_status = get_adguardvpn_status(config, persist_last_good=False)
                return self.send_json(get_transparent_proxy_status(config, vpn_status))
            if self.path == "/api/automation/status":
                return self.send_json(get_automation_status(load_config()))
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
                debug_log_path = Path(config["logging"]["debug_log_file"])
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                kind = params.get("kind", ["combined"])[0]
                if kind == "debug":
                    return self.send_json(
                        {
                            "content": tail_file(debug_log_path, 200),
                            "path": str(debug_log_path),
                            "exists": debug_log_path.exists(),
                            "kind": "debug",
                            "debug_enabled": bool(config["logging"]["debug_enabled"]),
                        }
                    )
                return self.send_json(
                    {
                        "content": tail_file(log_path, 200),
                        "path": str(log_path),
                        "exists": log_path.exists(),
                        "kind": "main",
                        "debug": {
                            "content": tail_file(debug_log_path, 200),
                            "path": str(debug_log_path),
                            "exists": debug_log_path.exists(),
                            "enabled": bool(config["logging"]["debug_enabled"]),
                        },
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
                notify_automation_config_changed()
                generation = generate_script(config)
                vpn_status = get_adguardvpn_status(config, persist_last_good=False)
                transparent_proxy = reconcile_transparent_proxy(config, vpn_status=vpn_status, reason="config-save")
                return self.send_json({"config": config, "generation": generation, "transparent_proxy": transparent_proxy})
            if self.path == "/api/actions/generate-script":
                return self.send_json(generate_script(load_config()))
            if self.path == "/api/actions/check":
                return self.send_json(perform_http_check(load_config()))
            if self.path == "/api/actions/rotate":
                return self.send_json(run_rotation(load_config(), trigger="manual"))
            if self.path == "/api/actions/clear-logs":
                return self.send_json(clear_logs(load_config()))
            if self.path == "/api/automation/update":
                payload = update_automation_config(
                    load_config(),
                    enabled=body.get("enabled"),
                    check_interval=body.get("check_interval"),
                )
                return self.send_json(payload)
            if self.path == "/api/adguardvpn/connect":
                location = str(body.get("location", "")).strip() or None
                return self.send_json(connect_adguardvpn(load_config(), location))
            if self.path == "/api/adguardvpn/disconnect":
                return self.send_json(disconnect_adguardvpn(load_config()))
            if self.path == "/api/transparent-proxy/sync":
                config = load_config()
                vpn_status = get_adguardvpn_status(config, persist_last_good=False)
                return self.send_json(sync_transparent_proxy(config, vpn_status=vpn_status, reason="api"))
            if self.path == "/api/transparent-proxy/stop":
                return self.send_json(stop_transparent_proxy(load_config(), reason="api"))
            if self.path == "/api/autostart/apply":
                start_now = bool(body.get("start_now", False))
                return self.send_json(apply_autostart(load_config(), start_now=start_now))
            if self.path == "/api/autostart/remove":
                stop_now = bool(body.get("stop_now", True))
                return self.send_json(remove_autostart(load_config(), stop_now=stop_now))
            if self.path == "/api/actions/update-project":
                return self.send_json(run_project_update(load_config()))
            if self.path == "/api/actions/restart-panel":
                delay_seconds = max(1, int(body.get("delay_seconds", 2) or 2))
                return self.send_json(restart_panel(load_config(), delay_seconds=delay_seconds))

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

    def serve_asset(self, filename: str, content_type: str) -> None:
        path = ASSETS_DIR / filename
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


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> None:
    config = ensure_config()
    if len(sys.argv) > 1 and sys.argv[1] == "rotate":
        result = run_rotation(config, trigger="cli")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result.get("success") else 1)
    if len(sys.argv) > 1 and sys.argv[1] == "sync-transparent-proxy":
        vpn_status = get_adguardvpn_status(config, persist_last_good=False)
        result = sync_transparent_proxy(config, vpn_status=vpn_status, reason="cli")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result.get("success") else 1)
    if len(sys.argv) > 1 and sys.argv[1] == "stop-transparent-proxy":
        result = stop_transparent_proxy(config, reason="cli")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result.get("success") else 1)

    generate_script(config)
    try:
        startup_status = get_adguardvpn_status(config, persist_last_good=False)
        reconcile_transparent_proxy(config, vpn_status=startup_status, reason="startup")
    except Exception as exc:  # noqa: BLE001
        append_debug_log(config, "transparent_proxy.startup.failed", error=str(exc))
    host = config["panel"]["host"]
    port = config["panel"]["port"]
    server = ReusableThreadingHTTPServer((host, port), PanelHandler)
    automation_thread, automation_stop_event = start_automation_worker()
    print(f"VPN panel running on http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        automation_stop_event.set()
        notify_automation_config_changed()
        automation_thread.join(timeout=2)
        server.server_close()


if __name__ == "__main__":
    main()
