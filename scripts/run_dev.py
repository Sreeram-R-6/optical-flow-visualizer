"""Windows-friendly one-command bootstrap and supervised local servers."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]

def run(args: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(args, cwd=cwd, check=True)

def fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        if path.is_file():
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()

def main() -> None:
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11 or newer is required.')
    parser = argparse.ArgumentParser()
    parser.add_argument('--dev', action='store_true', help='Run Vite with hot reload')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ['npm_config_cache'] = str(ROOT/'.tools'/'npm-cache')
    node = shutil.which('node')
    if not node:
        candidates = list((ROOT / '.tools').glob('node-*-win-x64/node.exe'))
        if candidates:
            os.environ['PATH'] = str(candidates[-1].parent) + os.pathsep + os.environ.get('PATH','')
            node = str(candidates[-1])
    npm = shutil.which('npm.cmd') or shutil.which('npm')
    if not node or not npm:
        raise RuntimeError('Node.js 22 LTS is required. Install from https://nodejs.org and restart this terminal.')
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        run([sys.executable,'-m','venv',str(ROOT/'.venv')])
    stamp = ROOT / '.venv' / '.requirements-hash'
    req_hash = fingerprint([ROOT/'requirements.txt'])
    if not stamp.exists() or stamp.read_text() != req_hash:
        run([str(python),'-m','pip','install','-r','requirements.txt'])
        stamp.write_text(req_hash)
    front = ROOT / 'frontend'
    dependencies = front/'node_modules'/'.package-hash'
    package_hash = fingerprint([front/'package.json',front/'package-lock.json'])
    if not dependencies.exists() or dependencies.read_text() != package_hash:
        run([npm,'ci' if (front/'package-lock.json').exists() else 'install'], front)
        dependencies.write_text(fingerprint([front/'package.json',front/'package-lock.json']))
    build_stamp = front/'dist'/'.source-hash'
    build_hash = fingerprint(list((front/'src').rglob('*'))+[front/'package.json',front/'package-lock.json',front/'index.html',front/'vite.config.mjs',front/'tsconfig.json'])
    if not args.dev and (not build_stamp.exists() or build_stamp.read_text()!=build_hash):
        run([npm,'run','build'],front)
        build_stamp.write_text(build_hash)
    for port in ([8000,5173] if args.dev else [8000]):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1',port))
            except OSError as exc:
                raise RuntimeError(f'Port {port} is busy. Stop the existing server before launching.') from exc
    children = []
    try:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        children.append(subprocess.Popen([str(python),'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000'],cwd=ROOT, creationflags=flags))
        if args.dev:
            children.append(subprocess.Popen([node,str(front/'node_modules'/'vite'/'bin'/'vite.js'),'--configLoader','native','--host','127.0.0.1','--port','5173','--strictPort'],cwd=front, creationflags=flags))
        url = 'http://127.0.0.1:5173' if args.dev else 'http://127.0.0.1:8000'
        print(f'Optical Flow Visualizer: {url}\nPress Ctrl+C to stop all servers.',flush=True)
        for _ in range(100):
            if any(c.poll() is not None for c in children):
                raise RuntimeError('A server exited during startup. See output above.')
            try:
                urllib.request.urlopen(url, timeout=.5).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Application did not become ready.')
        if not args.no_browser:
            webbrowser.open(url)
        while all(c.poll() is None for c in children):
            time.sleep(.3)
    except KeyboardInterrupt:
        print('\nStopping servers…')
    finally:
        for child in children:
            if child.poll() is None:
                # CTRL_BREAK lets Uvicorn close serial and websocket resources.
                if os.name == 'nt':
                    child.send_signal(__import__('signal').CTRL_BREAK_EVENT)
                else:
                    child.terminate()
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Launch failed: {exc}',file=sys.stderr)
        sys.exit(1)
