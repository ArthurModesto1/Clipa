"""Platform normalization, yt-dlp configuration and actionable errors."""
from contextlib import contextmanager
import atexit
import os
from pathlib import Path
import re
import shutil
import ssl
import sys
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit, urlunsplit

import yt_dlp
from yt_dlp.utils import DownloadError


class AppError(Exception):
    def __init__(self, message, code='invalid_request', hint='', status=400):
        super().__init__(message)
        self.message, self.code, self.hint, self.status = message, code, hint, status


class Cancelled(Exception):
    pass


_trust_lock = threading.Lock()
_trust_ready = False


def configure_system_certificates():
    """Share Windows' trust roots with libcurl without disabling verification."""
    global _trust_ready
    with _trust_lock:
        if _trust_ready or sys.platform != 'win32':
            return
        if os.environ.get('REQUESTS_CA_BUNDLE') or os.environ.get('CURL_CA_BUNDLE'):
            _trust_ready = True
            return
        certificates = ssl.create_default_context().get_ca_certs(binary_form=True)
        if not certificates:
            return
        with tempfile.NamedTemporaryFile(mode='w', encoding='ascii', prefix='clipa-ca-',
                                         suffix='.pem', delete=False) as bundle:
            for certificate in certificates:
                bundle.write(ssl.DER_cert_to_PEM_cert(certificate))
        os.environ['REQUESTS_CA_BUNDLE'] = bundle.name
        os.environ['CURL_CA_BUNDLE'] = bundle.name
        atexit.register(lambda: Path(bundle.name).unlink(missing_ok=True))
        _trust_ready = True


def normalize_url(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise AppError('Cole o link de um vídeo ou de uma publicação.')
    value = value.strip()
    if not re.match(r'^https?://', value, re.I):
        value = 'https://' + value
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower()
        if parsed.username or parsed.password or parsed.port not in (None, 80, 443):
            raise ValueError()
    except ValueError as error:
        raise AppError('O link informado é inválido.') from error
    domains = {'youtube.com': 'YouTube', 'youtu.be': 'YouTube', 'x.com': 'X',
               'twitter.com': 'X', 'instagram.com': 'Instagram', 'tiktok.com': 'TikTok'}
    platform = next((name for domain, name in domains.items()
                     if host == domain or host.endswith('.' + domain)), None)
    if not platform:
        raise AppError('Use um link do YouTube, X, Instagram ou TikTok.', code='unsupported_platform')
    path = parsed.path.rstrip('/')
    valid = {
        'YouTube': bool(path and (host == 'youtu.be' or path == '/watch' and parse_qs(parsed.query).get('v') or
                                re.match(r'^/(shorts|live|embed)/[^/]+$', path))),
        'X': bool(re.search(r'/status/\d+', path)),
        'Instagram': bool(re.match(r'^/(p|reel|reels|tv)/[^/]+', path)),
        'TikTok': bool(re.search(r'/video/\d+', path) or host in ('vm.tiktok.com', 'vt.tiktok.com') and path
                       or path.startswith('/t/')),
    }
    if not valid[platform]:
        raise AppError('Cole o link de uma publicação, não de um perfil ou de uma página inicial.')
    if platform == 'X':
        host = 'x.com'
        path = re.sub(r'/(video|photo)/\d+/?$', '', path)
    if platform == 'Instagram':
        host = 'www.instagram.com'
        path = path.replace('/reels/', '/reel/', 1) + '/'
    query = parsed.query if platform in ('YouTube', 'TikTok') else ''
    return urlunsplit(('https', host, path, query, '')), platform


def tool_path(name):
    folder = os.environ.get('CLIPA_FFMPEG_DIR')
    if folder and name in ('ffmpeg', 'ffprobe'):
        candidate = Path(folder) / (name + ('.exe' if sys.platform == 'win32' else ''))
        return str(candidate) if candidate.is_file() else None
    if name == 'node' and os.environ.get('CLIPA_NODE_PATH'):
        candidate = Path(os.environ['CLIPA_NODE_PATH'])
        return str(candidate) if candidate.is_file() else None
    return shutil.which(name)


def capabilities():
    return dict(download_dir=str(Path.home() / 'Downloads'),
                ffmpeg=bool(tool_path('ffmpeg') and tool_path('ffprobe')),
                node=bool(tool_path('node')), yt_dlp_version=yt_dlp.version.__version__)


@contextmanager
def session_options(data, logger):
    configure_system_certificates()
    options = dict(quiet=True, noprogress=True, logger=logger, noplaylist=True,
                   playlist_items='1', retries=3, fragment_retries=3, extractor_retries=2,
                   socket_timeout=25, cachedir=False, windowsfilenames=True, trim_file_name=160)
    node = tool_path('node')
    if node:
        options['js_runtimes'] = {'node': {'path': node}}
    if sys.platform == 'win32':
        options['compat_opts'] = {'no-certifi'}
    ffmpeg = tool_path('ffmpeg')
    if ffmpeg:
        options['ffmpeg_location'] = str(Path(ffmpeg).parent)
    cookie_path = data.get('cookie_file')
    if cookie_path is not None and not isinstance(cookie_path, str):
        raise AppError('Selecione um arquivo de sessão válido.')
    # yt-dlp saves cookies on exit. A private temporary copy avoids modifying
    # the selected file or corrupting it during concurrent requests.
    with tempfile.TemporaryDirectory(prefix='clipa-session-') as temporary:
        if cookie_path:
            try:
                source = Path(cookie_path).expanduser()
                if not source.is_file() or source.stat().st_size > 4 * 1024 * 1024:
                    raise ValueError()
                with source.open('r', encoding='utf-8-sig') as stream:
                    if stream.readline().strip() not in ('# Netscape HTTP Cookie File', '# HTTP Cookie File'):
                        raise ValueError()
                destination = Path(temporary) / 'cookies.txt'
                destination.write_text(source.read_text(encoding='utf-8-sig'), encoding='utf-8')
                options['cookiefile'] = str(destination)
            except (OSError, ValueError, UnicodeError) as error:
                raise AppError('O arquivo de sessão não pôde ser lido.', code='invalid_cookies',
                               hint='Selecione cookies no formato Netscape (.txt) em Configurações.') from error
        yield options


def first_media(info):
    if not info:
        raise AppError('Nenhum vídeo foi encontrado nesta publicação.', code='no_media', status=422)
    if info.get('_type') in ('playlist', 'multi_video') or 'entries' in info:
        entry = next((entry for entry in info.get('entries') or [] if entry), None)
        return first_media(entry)
    if not info.get('formats') and not info.get('url'):
        raise AppError('Esta publicação não contém um vídeo disponível.', code='no_media', status=422)
    if info.get('is_live'):
        raise AppError('Aguarde a transmissão ao vivo terminar.', code='live_video', status=422)
    return info


def extract_media(url, platform, options, download=False):
    attempts = [options]
    if platform == 'X':
        attempts.append({**options, 'extractor_args': {'twitter': {'api': ['syndication']}}})
    for index, attempt in enumerate(attempts):
        with yt_dlp.YoutubeDL(attempt) as ydl:
            try:
                info = first_media(ydl.extract_info(url, download=False))
            except DownloadError:
                if index + 1 < len(attempts):
                    continue
                raise
            if download:
                return ydl.process_ie_result(info, download=True)
            return info


def validate_download(data):
    mode = data.get('mode', 'video')
    quality = data.get('quality', '1080' if mode == 'video' else '192')
    fmt = data.get('format', 'mp4' if mode == 'video' else 'mp3')
    if mode not in ('video', 'audio'):
        raise AppError('Escolha vídeo ou áudio.')
    formats = ('mp4', 'mkv', 'webm') if mode == 'video' else ('mp3', 'aac', 'opus', 'flac', 'wav')
    qualities = ('360', '480', '720', '1080', '1440', '2160') if mode == 'video' else ('128', '192', '256', '320')
    if fmt not in formats or quality not in qualities:
        raise AppError('Formato ou qualidade inválidos.')
    if not capabilities()['ffmpeg']:
        raise AppError('O FFmpeg não foi encontrado.', code='missing_ffmpeg', status=503,
                       hint='Instale FFmpeg e FFprobe e reabra o Clipa. Consulte o README.')
    value = data.get('output_dir') or str(Path.home() / 'Downloads')
    if not isinstance(value, str):
        raise AppError('Escolha uma pasta de destino válida.')
    try:
        folder = Path(value).expanduser()
        if not folder.is_absolute():
            raise ValueError()
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=folder):
            pass
    except (OSError, ValueError) as error:
        raise AppError('Não foi possível gravar na pasta de destino.', code='invalid_directory',
                       hint='Escolha outra pasta ou verifique a permissão de escrita.') from error
    return folder


def download_options(data, out_dir):
    mode = data.get('mode', 'video')
    quality = data.get('quality', '1080' if mode == 'video' else '192')
    fmt = data.get('format', 'mp4' if mode == 'video' else 'mp3')
    options = {'outtmpl': str(out_dir / '%(title).140s [%(id)s].%(ext)s')}
    if mode == 'audio':
        options.update(format='bestaudio/best', postprocessors=[{
            'key': 'FFmpegExtractAudio', 'preferredcodec': fmt,
            'preferredquality': quality if fmt not in ('wav', 'flac') else '0',
        }])
    else:
        options.update(
            # ? accepts social posts whose extractors cannot report a height.
            format=f'bv*[height<=?{quality}]+ba/b[height<=?{quality}]',
            merge_output_format=fmt,
            postprocessors=[{'key': 'FFmpegVideoConvertor', 'preferedformat': fmt}],
        )
    return options


def friendly_error(error, platform):
    if isinstance(error, AppError):
        return error
    text = str(error).lower()
    if any(word in text for word in ('cookie', 'login', 'log in', 'sign in', 'authentication', 'private', 'age-restricted')):
        return AppError(f'{platform} exige uma sessão com acesso a esta publicação.', 'login_required',
                        'Em Configurações, selecione um arquivo de cookies da sua sessão e tente novamente.', 422)
    if any(word in text for word in ('429', 'rate limit', 'too many requests')):
        return AppError(f'{platform} limitou as tentativas.', 'rate_limited',
                        'Aguarde alguns minutos antes de tentar novamente.', 429)
    if any(word in text for word in ('403', 'blocked', 'captcha', 'impersonat', 'challenge')):
        return AppError(f'{platform} bloqueou o acesso automático a este link.', 'platform_blocked',
                        'Abra o link no navegador. Se ele funcionar, configure sua sessão e tente novamente.', 422)
    if any(word in text for word in ('not available', 'unavailable', 'not found', '404', 'no video', 'does not contain')):
        return AppError('O vídeo está indisponível ou a publicação não contém vídeo.', 'unavailable',
                        'Confira se o link abre um vídeo no navegador.', 422)
    if any(word in text for word in ('certificate', 'ssl:')):
        return AppError('Não foi possível verificar a conexão segura.', 'certificate_error',
                        'Confira os certificados da rede. O Clipa mantém a verificação HTTPS ativa.', 502)
    if any(word in text for word in ('timed out', 'timeout', 'resolve', 'connection', 'network')):
        return AppError(f'Não foi possível conectar ao {platform}.', 'network_error',
                        'Confira a conexão e tente novamente.', 502)
    if isinstance(error, OSError):
        return AppError('Não foi possível salvar ou processar o arquivo.', 'file_error',
                        'Confira a pasta de destino e se há espaço disponível.', 500)
    return AppError(f'Não foi possível processar este vídeo do {platform}.', 'extraction_failed',
                    'Confira o link, atualize o yt-dlp e tente novamente. Detalhes no log local.', 422)
