"""Authenticated local API for the Electron application."""
import argparse
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import threading
import uuid
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import BadRequest, UnsupportedMediaType
from werkzeug.serving import make_server

from media import (AppError, Cancelled, capabilities, download_options, extract_media,
                   friendly_error, normalize_url, session_options, validate_download)

log_dir = Path(os.environ.get('CLIPA_LOG_DIR') or
               Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'Clipa')
log_dir.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger('clipa')
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(RotatingFileHandler(log_dir / 'backend.log', maxBytes=1_000_000,
                                         backupCount=2, encoding='utf-8'))

API_TOKEN = os.environ.get('CLIPA_API_TOKEN') or secrets.token_urlsafe(32)
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024
CORS(app, origins=['null'], allow_headers=['Content-Type', 'X-Clipa-Token'])
jobs = {}
jobs_lock = threading.RLock()
MAX_ACTIVE, MAX_JOBS = 2, 100


@app.before_request
def authenticate():
    if request.method == 'OPTIONS' or request.path == '/ping':
        return None
    token = request.headers.get('X-Clipa-Token', '')
    if not token.isascii() or not hmac.compare_digest(token, API_TOKEN):
        return jsonify(error='Sessão inválida. Reabra o Clipa.', code='unauthorized'), 401


@app.errorhandler(AppError)
def handle_app_error(error):
    return jsonify(error=error.message, code=error.code, hint=error.hint), error.status


@app.errorhandler(BadRequest)
@app.errorhandler(UnsupportedMediaType)
def handle_bad_json(_error):
    return jsonify(error='Envie um objeto JSON válido.', code='invalid_request'), 400


def payload():
    data = request.get_json()
    if not isinstance(data, dict):
        raise AppError('Envie um objeto JSON válido.')
    return data


def update_job(job_id, **changes):
    with jobs_lock:
        jobs[job_id].update(changes)


def progress_hook(data, job_id):
    with jobs_lock:
        if jobs[job_id]['cancel'].is_set():
            raise Cancelled()
    if data['status'] == 'downloading':
        total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
        speed, eta = data.get('speed') or 0, data.get('eta')
        update_job(job_id, status='downloading',
                   percent=min(98, round(data.get('downloaded_bytes', 0) / total * 100, 1)) if total else 0,
                   indeterminate=not bool(total), speed=f'{speed / 1024 / 1024:.1f} MB/s' if speed else '—',
                   eta=f'{eta}s' if eta is not None else '—')
    elif data['status'] == 'finished':
        update_job(job_id, status='processing', percent=99, indeterminate=True, speed='—', eta='—')


@app.get('/ping')
def ping():
    return jsonify(ok=True)


@app.get('/settings')
def settings():
    return jsonify(capabilities())


@app.post('/info')
def info():
    data = payload()
    url, platform = normalize_url(data.get('url'))
    try:
        with session_options(data, logger) as options:
            result = extract_media(url, platform, options)
        seconds = int(result.get('duration') or 0)
        return jsonify(title=result.get('title') or 'Sem título',
                       channel=result.get('uploader') or result.get('channel') or platform,
                       duration=f'{seconds // 60}:{seconds % 60:02d}' if seconds else 'Duração indisponível',
                       thumbnail=result.get('thumbnail'), platform=platform, url=url, id=result.get('id'))
    except Exception as error:
        logger.exception('Metadata extraction failed for %s', platform)
        raise friendly_error(error, platform) from error


def run_download(job_id, data, url, platform, out_dir):
    try:
        with session_options(data, logger) as options:
            options.update(download_options(data, out_dir))
            options['progress_hooks'] = [lambda d: progress_hook(d, job_id)]
            result = extract_media(url, platform, options, download=True)
        update_job(job_id, status='done', percent=100, indeterminate=False, speed='—', eta='—',
                   title=result.get('title') or 'Arquivo', output_dir=str(out_dir))
    except Cancelled:
        update_job(job_id, status='cancelled', percent=0, indeterminate=False)
    except Exception as error:
        logger.exception('Download failed: %s (%s)', job_id, platform)
        error = friendly_error(error, platform)
        update_job(job_id, status='error', percent=0, indeterminate=False,
                   error=error.message, code=error.code, hint=error.hint)


@app.post('/download')
def download():
    data = payload()
    url, platform = normalize_url(data.get('url'))
    out_dir = validate_download(data)
    job_id = data.get('download_id') or uuid.uuid4().hex
    if not isinstance(job_id, str) or not 1 <= len(job_id) <= 80 or not all(
            char.isalnum() or char in '_-' for char in job_id):
        raise AppError('Identificador de download inválido.')
    with jobs_lock:
        if job_id in jobs:
            raise AppError('Este download já foi iniciado.', status=409)
        active = [job for job in jobs.values() if job['status'] in ('starting', 'downloading', 'processing')]
        if len(active) >= MAX_ACTIVE:
            raise AppError('Aguarde um dos downloads terminar.', code='busy', status=429)
        while len(jobs) >= MAX_JOBS:
            oldest = next(key for key, job in jobs.items()
                          if job['status'] not in ('starting', 'downloading', 'processing'))
            del jobs[oldest]
        jobs[job_id] = dict(status='starting', percent=0, indeterminate=True,
                            speed='—', eta='—', cancel=threading.Event())
    threading.Thread(target=run_download, args=(job_id, data, url, platform, out_dir), daemon=True).start()
    return jsonify(download_id=job_id, status='started'), 202


@app.get('/progress/<job_id>')
def progress(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return jsonify(error='Download não encontrado. Inicie novamente.', code='not_found'), 404
        return jsonify({key: value for key, value in job.items() if key != 'cancel'})


@app.post('/cancel/<job_id>')
def cancel(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise AppError('Download não encontrado.', status=404)
        job['cancel'].set()
    return jsonify(ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=57291)
    args = parser.parse_args()
    server = make_server('127.0.0.1', args.port, app, threaded=True)
    print('CLIPA_READY ' + json.dumps({'port': server.server_port, 'pid': os.getpid()}), flush=True)
    server.serve_forever()
