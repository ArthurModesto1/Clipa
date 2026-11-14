import logging
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
os.environ['CLIPA_LOG_DIR'] = str(Path(tempfile.gettempdir()) / 'clipa-tests')
import media
import server
from yt_dlp.utils import DownloadError


class PlatformTests(unittest.TestCase):
    def test_normalize_all_platforms(self):
        examples = [
            ('https://youtu.be/aeJzEJ8pcXg', 'YouTube'),
            ('youtube.com/shorts/abcdef', 'YouTube'),
            ('https://twitter.com/user/status/123/video/1?s=20', 'X'),
            ('https://www.instagram.com/reels/ABC/?igsh=tracking', 'Instagram'),
            ('https://www.tiktok.com/@user/video/123', 'TikTok'),
            ('https://vm.tiktok.com/ABCD/', 'TikTok'),
            ('https://www.tiktok.com/t/ABCD/', 'TikTok'),
        ]
        for url, expected in examples:
            with self.subTest(url=url):
                normalized, platform = media.normalize_url(url)
                self.assertEqual(platform, expected)
                self.assertTrue(normalized.startswith('https://'))
        self.assertEqual(media.normalize_url(examples[2][0])[0], 'https://x.com/user/status/123')
        self.assertEqual(media.normalize_url(examples[3][0])[0], 'https://www.instagram.com/reel/ABC/')

    def test_reject_profiles_spoofed_hosts_and_local_urls(self):
        for value in [None, [], '', 'file:///tmp/test.mp4', 'https://127.0.0.1/a',
                      'https://instagram.com.evil.test/reel/ABC', 'https://x.com/user',
                      'https://instagram.com/user/', 'https://tiktok.com/@user',
                      'https://user:secret@youtube.com/watch?v=x', 'https://youtube.com:99/watch?v=x']:
            with self.subTest(value=value), self.assertRaises(media.AppError):
                media.normalize_url(value)

    def test_social_posts_without_height_still_match(self):
        options = media.download_options({'mode': 'video', 'quality': '1080', 'format': 'mp4'}, Path('/output'))
        with media.yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            selector = ydl.build_format_selector(options['format'])
            formats = [{'format_id': 'social', 'url': 'https://media.example/video.mp4',
                        'ext': 'mp4', 'vcodec': 'h264', 'acodec': 'aac'}]
            selected = list(selector({'formats': formats, 'has_merged_format': True, 'incomplete_formats': False}))
        self.assertEqual(selected[0]['format_id'], 'social')

    def test_x_uses_syndication_when_graphql_fails(self):
        first, second = MagicMock(), MagicMock()
        first.extract_info.side_effect = DownloadError('HTTP Error 403')
        second.extract_info.return_value = {'id': '123', 'title': 'Test', 'formats': [{}]}
        with patch('media.yt_dlp.YoutubeDL') as factory:
            factory.side_effect = [MagicMock(__enter__=lambda _: first), MagicMock(__enter__=lambda _: second)]
            result = media.extract_media('https://x.com/u/status/123', 'X', {})
            self.assertEqual(result['id'], '123')
            self.assertEqual(factory.call_args.kwargs, {})
            self.assertEqual(factory.call_args.args[0]['extractor_args']['twitter']['api'], ['syndication'])

    def test_carousel_uses_first_video_and_handles_missing_duration(self):
        item = {'id': 'a', 'formats': [{}]}
        self.assertEqual(media.first_media({'_type': 'playlist', 'entries': [None, item]}), item)
        with self.assertRaises(media.AppError):
            media.first_media({'_type': 'playlist', 'entries': []})

    def test_live_streams_are_rejected(self):
        with self.assertRaises(media.AppError) as error:
            media.first_media({'url': 'https://test/video', 'is_live': True})
        self.assertEqual(error.exception.code, 'live_video')

    def test_selected_cookie_file_is_never_modified(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'session.txt'
            content = '# Netscape HTTP Cookie File\n'
            source.write_text(content, encoding='utf-8')
            with media.session_options({'cookie_file': str(source)}, logging.getLogger('test')) as options:
                copy = Path(options['cookiefile'])
                self.assertNotEqual(copy, source)
                copy.write_text('changed by extractor', encoding='utf-8')
            self.assertEqual(source.read_text(encoding='utf-8'), content)
            self.assertFalse(copy.exists())

    def test_invalid_cookie_file_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'session.txt'
            source.write_text('not a cookie file', encoding='utf-8')
            with self.assertRaises(media.AppError) as error:
                with media.session_options({'cookie_file': str(source)}, logging.getLogger('test')):
                    pass
            self.assertEqual(error.exception.code, 'invalid_cookies')

    def test_windows_cookie_bom_is_normalized_in_private_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'session.txt'
            source.write_text('# Netscape HTTP Cookie File\n', encoding='utf-8-sig')
            with media.session_options({'cookie_file': str(source)}, logging.getLogger('test')) as options:
                self.assertFalse(Path(options['cookiefile']).read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertTrue(source.read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_error_classification(self):
        for text, code in [('Login required', 'login_required'), ('HTTP Error 429', 'rate_limited'),
                           ('HTTP Error 403', 'platform_blocked'), ('Connection timed out', 'network_error'),
                           ('SSL: certificate verify failed', 'certificate_error')]:
            self.assertEqual(media.friendly_error(Exception(text), 'Instagram').code, code)

    def test_explicit_ca_bundle_is_preserved(self):
        with patch.dict(os.environ, {'REQUESTS_CA_BUNDLE': 'user-selected.pem'}), \
             patch.object(media, '_trust_ready', False), patch.object(media.sys, 'platform', 'win32'), \
             patch('media.ssl.create_default_context') as context:
            media.configure_system_certificates()
            context.assert_not_called()
            self.assertEqual(os.environ['REQUESTS_CA_BUNDLE'], 'user-selected.pem')

    def test_windows_root_export_keeps_verification_enabled(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(media, '_trust_ready', False), \
             patch.object(media.sys, 'platform', 'win32'), \
             patch('media.ssl.create_default_context') as context, patch('media.atexit.register'):
            context.return_value.get_ca_certs.return_value = [b'test-certificate']
            media.configure_system_certificates()
            bundle = Path(os.environ['REQUESTS_CA_BUNDLE'])
            try:
                self.assertIn('BEGIN CERTIFICATE', bundle.read_text())
                self.assertEqual(os.environ['CURL_CA_BUNDLE'], str(bundle))
            finally:
                bundle.unlink()


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        self.headers = {'X-Clipa-Token': server.API_TOKEN}
        server.jobs.clear()

    def post(self, route, data):
        return self.client.post(route, json=data, headers=self.headers)

    def test_auth_required_even_for_local_requests(self):
        self.assertEqual(self.client.get('/settings').status_code, 401)
        self.assertEqual(self.client.get('/ping').status_code, 200)
        self.assertEqual(self.client.get('/settings', headers=self.headers).status_code, 200)

    def test_malformed_payloads_are_json_errors(self):
        for payload in [[], 'invalid', 123]:
            self.assertEqual(self.post('/info', payload).status_code, 400)
        response = self.client.post('/info', data='{', content_type='application/json', headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json)

    def test_metadata_with_unknown_duration(self):
        with patch('server.extract_media', return_value={'id': '1', 'title': '<script>test</script>', 'duration': None}):
            response = self.post('/info', {'url': 'https://instagram.com/reel/ABC/'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['duration'], 'Duração indisponível')
        self.assertEqual(response.json['title'], '<script>test</script>')

    def test_bad_format_rejected_before_creating_job(self):
        response = self.post('/download', {'url': 'https://x.com/u/status/123', 'format': 'exe'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(server.jobs)

    def test_missing_ffmpeg_reports_503(self):
        with patch('media.capabilities', return_value={'ffmpeg': False}):
            response = self.post('/download', {'url': 'https://youtu.be/abc'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json['code'], 'missing_ffmpeg')

    def test_download_start_completion_and_snapshot(self):
        with tempfile.TemporaryDirectory() as directory, patch('media.capabilities', return_value={'ffmpeg': True}), \
             patch('server.threading.Thread') as thread:
            response = self.post('/download', {'url': 'https://x.com/u/status/123', 'mode': 'audio',
                                              'format': 'mp3', 'quality': '192', 'output_dir': directory})
            self.assertEqual(response.status_code, 202)
            job_id = response.json['download_id']
            self.assertTrue(thread.call_args.kwargs['daemon'])
            self.assertNotIn('cancel', self.client.get('/progress/' + job_id, headers=self.headers).json)
            with patch('server.extract_media', return_value={'title': 'Completed'}):
                server.run_download(*thread.call_args.kwargs['args'])
            result = self.client.get('/progress/' + job_id, headers=self.headers).json
            self.assertEqual(result['status'], 'done')
            self.assertEqual(result['output_dir'], directory)

    def test_missing_job_is_404(self):
        self.assertEqual(self.client.get('/progress/missing', headers=self.headers).status_code, 404)

    def test_cancel_flag_interrupts_download_hook(self):
        server.jobs['test'] = {'cancel': threading.Event(), 'status': 'downloading'}
        self.assertEqual(self.post('/cancel/test', {}).status_code, 200)
        with self.assertRaises(media.Cancelled):
            server.progress_hook({'status': 'downloading'}, 'test')

    def test_concurrency_limit_and_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as directory, patch('media.capabilities', return_value={'ffmpeg': True}), \
             patch('server.threading.Thread'):
            data = dict(url='https://youtu.be/abc', output_dir=directory, download_id='first')
            self.assertEqual(self.post('/download', data).status_code, 202)
            self.assertEqual(self.post('/download', data).status_code, 409)
            data['download_id'] = 'second'
            self.assertEqual(self.post('/download', data).status_code, 202)
            data['download_id'] = 'third'
            self.assertEqual(self.post('/download', data).status_code, 429)


if __name__ == '__main__':
    unittest.main()
