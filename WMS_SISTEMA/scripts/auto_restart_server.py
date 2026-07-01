"""
Auto-restart helper for the local test server (Windows).

Usage:
  python scripts\auto_restart_server.py

Behavior:
 - Starts `run_test.py` as a child process using the current Python interpreter.
 - Watches the workspace (WMS_SISTEMA) for file changes (polling-based).
 - When a change is detected in tracked extensions, kills and restarts the child process.

Note: this is a simple polling watcher to avoid extra dependencies. Run it in a dedicated terminal.
"""
import os
import sys
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = ROOT / 'run_test.py'
WATCH_EXTS = {'.py', '.html', '.css', '.js', '.json'}
POLL_INTERVAL = 1.0


def snapshot_mtimes(root: Path):
    mtimes = {}
    for p in root.rglob('*'):
        if p.suffix.lower() in WATCH_EXTS and p.is_file():
            try:
                mtimes[str(p)] = p.stat().st_mtime
            except Exception:
                pass
    return mtimes


def start_server():
    print('[auto-restart] Starting server...')
    python = sys.executable or 'python'
    # Start run_test.py in a new process
    p = subprocess.Popen([python, str(RUN_SCRIPT)], cwd=str(ROOT))
    return p


def stop_server(p: subprocess.Popen):
    if not p:
        return
    print(f'[auto-restart] Stopping server (pid={p.pid})...')
    try:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    except Exception:
        pass


def main():
    if not RUN_SCRIPT.exists():
        print(f'[auto-restart] Cannot find {RUN_SCRIPT}')
        sys.exit(1)

    mt0 = snapshot_mtimes(ROOT)
    child = start_server()
    try:
        while True:
            time.sleep(POLL_INTERVAL)
            mt1 = snapshot_mtimes(ROOT)
            if mt1 != mt0:
                print('[auto-restart] Change detected; restarting server...')
                stop_server(child)
                child = start_server()
                mt0 = mt1
    except KeyboardInterrupt:
        print('\n[auto-restart] Stopping on user request...')
    finally:
        stop_server(child)


if __name__ == '__main__':
    main()
