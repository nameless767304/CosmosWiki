# run.py
import subprocess
import sys
import os
import shutil
import signal
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("cosmos_wiki")

class ShutdownRequested(Exception):
    pass

def _handle_termination(signum, frame):
    raise ShutdownRequested()

def resolve_root_env():
    """Find the root env file, preferring .env over .env.local."""
    for filename in (".env", ".env.local"):
        if os.path.exists(filename):
            return filename
    return None

def terminate_process_tree(process, name):
    """Stop a subprocess and any children it spawned (npm/uvicorn --reload)."""
    if process is None or process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
    logger.info(f"{name} stopped.")

def run_servers():
    signal.signal(signal.SIGTERM, _handle_termination)

    # Sync root env file to frontend so Next.js picks up shared variables
    root_env = resolve_root_env()
    if root_env:
        shutil.copyfile(root_env, os.path.join("frontend", ".env.local"))
    else:
        logger.warning("No .env or .env.local found at project root.")

    backend_process = None
    frontend_process = None
    is_windows = sys.platform == "win32"

    try:
        logger.info("Starting backend server on port 8000...")
        backend_process = subprocess.Popen(
            ["uvicorn", "app.main:app", "--reload", "--port", "8000"],
            cwd="backend",
            shell=is_windows
        )

        logger.info("Starting frontend server on port 3000...")
        frontend_process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd="frontend",
            shell=is_windows
        )

        # Watch both processes together; stop everything if either dies early
        while True:
            backend_exit = backend_process.poll()
            frontend_exit = frontend_process.poll()

            if backend_exit is not None:
                logger.error(f"Backend exited unexpectedly (code {backend_exit}).")
                break
            if frontend_exit is not None:
                logger.error(f"Frontend exited unexpectedly (code {frontend_exit}).")
                break

            time.sleep(1)

    except (KeyboardInterrupt, ShutdownRequested):
        logger.info("Stopping all servers...")
    finally:
        terminate_process_tree(backend_process, "Backend")
        terminate_process_tree(frontend_process, "Frontend")
        logger.info("All servers stopped successfully.")

if __name__ == "__main__":
    run_servers()
