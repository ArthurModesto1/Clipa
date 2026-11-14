"""Build the native Python backend and collect local runtime executables."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    tools = {}
    for name in ('ffmpeg', 'ffprobe', 'node'):
        source = shutil.which(name)
        if not source:
            raise SystemExit(f'{name} não encontrado no PATH. Instale antes de empacotar.')
        tools[name] = Path(source)
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit('Instale python/requirements-build.txt no ambiente Python do projeto.')
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
        '--name', 'server', '--distpath', str(ROOT / 'python/dist'),
        '--workpath', str(ROOT / 'python/build'), '--specpath', str(ROOT / 'python'),
        '--collect-all', 'yt_dlp', '--collect-all', 'yt_dlp_ejs',
        '--collect-all', 'curl_cffi', str(ROOT / 'python/server.py'),
    ], check=True)
    destination = ROOT / 'tools'
    destination.mkdir(exist_ok=True)
    manifest = {}
    for name, source in tools.items():
        target = destination / (name + ('.exe' if sys.platform == 'win32' else ''))
        shutil.copy2(source, target)
        manifest[name] = subprocess.check_output(
            [str(source), '-version' if name != 'node' else '--version'],
            text=True, encoding='utf-8', errors='replace').splitlines()[0]
    (destination / 'versions.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Backend e ferramentas preparados para o electron-builder.')


if __name__ == '__main__':
    main()
