"""Optional live check; URLs and permissions are supplied by the developer."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from media import (download_options, extract_media, friendly_error, normalize_url,
                   session_options, validate_download)


def check(url, args):
    platform = 'Plataforma'
    try:
        normalized, platform = normalize_url(url)
        data = dict(mode='video', format='mp4', quality='720',
                    cookie_file=args.cookies, output_dir=str(Path(args.output_dir).resolve()))
        with session_options(data, logging.getLogger('smoke')) as options:
            options['socket_timeout'] = 15
            options['extractor_retries'] = 0
            if args.download:
                options.update(download_options(data, validate_download(data)))
                options['max_filesize'] = 30 * 1024 * 1024
            result = extract_media(normalized, platform, options, download=args.download)
        return dict(platform=platform, status='ok', title=result.get('title'),
                    duration=result.get('duration'), downloaded=args.download)
    except Exception as error:
        friendly = friendly_error(error, platform)
        return dict(platform=platform, status='error', code=friendly.code,
                    error=friendly.message, hint=friendly.hint)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('urls', nargs='+')
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--cookies', default='')
    parser.add_argument('--output-dir', default='.artifacts/smoke')
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda url: check(url, args), args.urls))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(0 if all(result['status'] == 'ok' for result in results) else 1)
