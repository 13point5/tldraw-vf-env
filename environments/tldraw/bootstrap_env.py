import asyncio
import atexit
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

NVM_INSTALL_URL = "https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh"
VALIDATOR_LOG_DIR = Path("outputs/validator")
VALIDATOR_LOG_PATH = VALIDATOR_LOG_DIR / "validator.log"
VALIDATOR_PID_PATH = VALIDATOR_LOG_DIR / "validator.pid"

_validator_process: subprocess.Popen | None = None
_validator_process_url: str | None = None


def run_blocking(fn, *args, **kwargs):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return fn(*args, **kwargs)
    else:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args, **kwargs)
            return future.result()


def _bash(cmd: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-lc", cmd],
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=True,
    )


def _is_localhost(host: str | None) -> bool:
    return host in {"localhost", "127.0.0.1", None}


def _is_url_live(url: str, timeout_s: float = 2.0) -> bool:
    try:
        request = Request(url, method="GET")
        with urlopen(request, timeout=timeout_s) as response:
            return 200 <= response.status < 400
    except Exception:
        return False


def _playwright_cache_dirs() -> list[Path]:
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_path and env_path != "0":
        return [Path(env_path)]
    return [
        Path.home() / ".cache" / "ms-playwright",
        Path.home() / "Library" / "Caches" / "ms-playwright",
    ]


def _has_playwright_chromium() -> bool:
    for base in _playwright_cache_dirs():
        if not base.exists():
            continue
        for child in base.iterdir():
            if child.is_dir() and child.name.startswith("chromium-"):
                return True
    return False


def ensure_playwright_chromium(with_deps: bool = True) -> None:
    if _has_playwright_chromium():
        return
    cmd = [sys.executable, "-m", "playwright", "install"]
    if with_deps:
        cmd.append("--with-deps")
    cmd.append("chromium")
    try:
        subprocess.run(cmd, check=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Failed to install Playwright Chromium. Ensure network access and "
            "system dependencies are available."
        ) from exc


def ensure_node_via_nvm(node_version_major: str = "24") -> None:
    nvm_sh = Path.home() / ".nvm" / "nvm.sh"
    if not nvm_sh.exists():
        _bash(f"curl -o- {NVM_INSTALL_URL} | bash")
    _bash(f'. "{nvm_sh}" && nvm install {node_version_major}')

    node_version = _bash(f'. "{nvm_sh}" && node -v').stdout.strip()
    npm_version = _bash(f'. "{nvm_sh}" && npm -v').stdout.strip()

    if not node_version.startswith(f"v{node_version_major}."):
        raise RuntimeError(
            f"Unexpected Node.js version {node_version}; expected v{node_version_major}.x"
        )
    npm_major = npm_version.split(".")[0]
    if not npm_major.isdigit() or int(npm_major) < 11:
        raise RuntimeError(f"Unexpected npm version {npm_version}; expected >=11.x")


def ensure_tldraw_agent_deps(agent_dir: Path) -> None:
    node_modules = agent_dir / "node_modules"
    if node_modules.exists():
        if (node_modules / ".pnpm").exists():
            shutil.rmtree(node_modules, ignore_errors=True)
            package_lock = agent_dir / "package-lock.json"
            if package_lock.exists():
                package_lock.unlink()
        else:
            return
    nvm_sh = Path.home() / ".nvm" / "nvm.sh"
    _bash(f'. "{nvm_sh}" && cd "{agent_dir}" && npm install --no-fund --no-audit')


def _terminate_validator_process() -> None:
    global _validator_process
    if _validator_process is None:
        return
    if _validator_process.poll() is None:
        _validator_process.terminate()
        try:
            _validator_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _validator_process.kill()


def _read_log_tail(max_lines: int = 60) -> str:
    if not VALIDATOR_LOG_PATH.exists():
        return ""
    try:
        lines = VALIDATOR_LOG_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    if not lines:
        return ""
    tail = lines[-max_lines:]
    return "\n".join(tail)


def ensure_validator_server(
    validator_url: str,
    agent_dir: Path,
    timeout_ms: int = 60000,
) -> None:
    global _validator_process, _validator_process_url

    if _is_url_live(validator_url):
        return

    parsed = urlparse(validator_url)
    if not _is_localhost(parsed.hostname):
        return

    port = parsed.port or 5173
    if _validator_process and _validator_process.poll() is None:
        if _validator_process_url == validator_url:
            return
        _terminate_validator_process()

    VALIDATOR_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = VALIDATOR_LOG_PATH.open("a", encoding="utf-8")

    nvm_sh = Path.home() / ".nvm" / "nvm.sh"
    cmd = (
        f'. "{nvm_sh}" && cd "{agent_dir}" && '
        f"npm run dev -- --host 127.0.0.1 --port {port} --strictPort"
    )
    _validator_process = subprocess.Popen(
        ["bash", "-lc", cmd],
        stdout=log_handle,
        stderr=log_handle,
        text=True,
    )
    _validator_process_url = validator_url
    VALIDATOR_PID_PATH.write_text(str(_validator_process.pid), encoding="utf-8")
    atexit.register(_terminate_validator_process)

    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        if _validator_process and _validator_process.poll() is not None:
            log_tail = _read_log_tail()
            raise RuntimeError(
                "Validator server exited before it became ready. "
                f"Last logs:\n{log_tail}"
            )
        if _is_url_live(validator_url, timeout_s=2.0):
            return
        time.sleep(0.5)
    log_tail = _read_log_tail()
    raise RuntimeError(
        f"Validator server did not become ready: {validator_url}\n"
        f"Last logs:\n{log_tail}"
    )
