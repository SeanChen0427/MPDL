"""Run with: python3 -m unittest discover -s TubeDrop/tests -v"""
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location('tubedrop', Path(__file__).resolve().parents[1] / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class URLTests(unittest.TestCase):
    def test_supported_single_video_links(self):
        cases = [
            ('https://youtu.be/jNQXAC9IVRw?si=tracking', 'https://www.youtube.com/watch?v=jNQXAC9IVRw'),
            ('https://m.youtube.com/watch?v=jNQXAC9IVRw&list=playlist', 'https://www.youtube.com/watch?v=jNQXAC9IVRw'),
            ('https://youtube.com/shorts/jNQXAC9IVRw', 'https://www.youtube.com/watch?v=jNQXAC9IVRw'),
            ('https://youtube.com/live/jNQXAC9IVRw', 'https://www.youtube.com/watch?v=jNQXAC9IVRw'),
            ('https://youtube.com/embed/jNQXAC9IVRw', 'https://www.youtube.com/watch?v=jNQXAC9IVRw'),
            ('https://www.instagram.com/reel/Chunk8-jurw/?igsh=abc#tracking', 'https://www.instagram.com/reel/Chunk8-jurw/'),
            ('https://instagram.com/p/BQ0eAlwhDrw/?img_index=3', 'https://www.instagram.com/p/BQ0eAlwhDrw/'),
            ('https://www.instagram.com/reels/Cop84x6u7CP/', 'https://www.instagram.com/reel/Cop84x6u7CP/'),
            ('https://instagram.com/marvelskies.fc/reel/CWqAgUZgCku/', 'https://www.instagram.com/reel/CWqAgUZgCku/'),
            ('https://m.instagram.com/tv/BkfuX9UB-eK/', 'https://www.instagram.com/tv/BkfuX9UB-eK/'),
            ('https://instagram.com/p/9o6LshA7zy/embed/', 'https://www.instagram.com/p/9o6LshA7zy/'),
            ('https://m.facebook.com/watch/?v=647537299265662&ref=sharing', 'https://www.facebook.com/watch/?v=647537299265662'),
            ('https://www.facebook.com/video.php?v=637842556329505&fref=nf', 'https://www.facebook.com/watch/?v=637842556329505'),
            ('https://facebook.com/video/embed?video_id=637842556329505', 'https://www.facebook.com/watch/?v=637842556329505'),
            ('https://www.facebook.com/reel/1195289147628387/?mibextid=abc', 'https://www.facebook.com/reel/1195289147628387/'),
            ('https://zh-tw.facebook.com/cnn/videos/10155529876156509/', 'https://www.facebook.com/cnn/videos/10155529876156509/'),
            ('https://facebook.com/page/videos/vb.123/456/?type=2', 'https://www.facebook.com/page/videos/vb.123/456/'),
            ('https://facebook.com/page/posts/pfbidAbC123?mibextid=abc', 'https://www.facebook.com/page/posts/pfbidAbC123/'),
            ('https://facebook.com/groups/123/permalink/456/', 'https://www.facebook.com/groups/123/permalink/456/'),
            ('https://facebook.com/groups/123/posts/d41d8cd9/456/', 'https://www.facebook.com/groups/123/posts/d41d8cd9/456/'),
            ('https://m.facebook.com/story.php?story_fbid=123&id=456&ref=abc', 'https://www.facebook.com/story.php?story_fbid=123&id=456'),
            ('https://facebook.com/permalink.php?story_fbid=pfbidAbC123&id=456', 'https://www.facebook.com/permalink.php?story_fbid=pfbidAbC123&id=456'),
            ('https://fb.watch/Abc_123-/?mibextid=abc', 'https://fb.watch/Abc_123-/'),
            ('https://www.facebook.com/share/r/AbC123/?mibextid=abc', 'https://www.facebook.com/share/r/AbC123/'),
            ('https://facebook.com/share/v/AbC123/', 'https://www.facebook.com/share/v/AbC123/'),
            ('https://facebook.com/share/p/AbC123/', 'https://www.facebook.com/share/p/AbC123/'),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(server.normalize_url(raw), expected)
                self.assertEqual(server.normalize_url(expected), expected)

    def test_rejects_other_sites_profiles_and_unsafe_urls(self):
        cases = [None, 123, '', 'x' * 2049,
            'https://youtube.com/playlist?list=abc', 'https://youtu.be/bad-id',
            'https://youtube.com.evil.test/watch?v=jNQXAC9IVRw',
            'https://instagram.com.evil.test/reel/abc/', 'https://evilinstagram.com/p/abc/',
            'https://facebook.com.evil.test/reel/123/', 'https://fb.watch.evil.test/abc/',
            'http://127.0.0.1/video', 'file:///tmp/video.mp4', 'ftp://facebook.com/reel/123/',
            'https://user:password@facebook.com/reel/123/', 'https://@instagram.com/p/abc/',
            'https://facebook.com:8765/reel/123/', 'https://facebook.com:invalid/reel/123/',
            'https://facebook.com/reel/12\n34/', 'https://facebook.com/reel/12 34/',
            'https://facebook.com\\@evil.test/reel/123/',
            'https://instagram.com/instagram/', 'https://instagram.com/stories/user/123/',
            'https://instagram.com/reels/audio/123/', 'https://instagram.com/reels/audio/',
            'https://instagram.com/share/reel/abc/', 'https://instagram.com/p/%2E%2E/',
            'https://facebook.com/page/', 'https://facebook.com/groups/123/',
            'https://facebook.com/photo.php?fbid=123', 'https://facebook.com/reel/not-a-number/',
            'https://facebook.com/flx/warn?u=https://evil.test',
            'https://facebook.com/share/r/../../login/', 'https://fb.watch/abc/extra/',
        ]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                server.normalize_url(raw)

    def test_share_redirects_cannot_leave_facebook(self):
        handler = server.FacebookRedirectHandler()
        req = Request('https://fb.watch/abc/')
        for target in ('https://evil.test/video', 'http://127.0.0.1/',
                       'file:///tmp/video', 'https://facebook.com:8765/reel/123/',
                       'https://instagram.com/p/abc/'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                handler.redirect_request(req, None, 302, 'Found', {}, target)
        redirected = handler.redirect_request(req, None, 302, 'Found', {}, 'https://www.facebook.com/reel/123/')
        self.assertEqual(redirected.full_url, 'https://www.facebook.com/reel/123/')

    def test_share_resolver_validates_final_video(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(server, 'build_opener', return_value=opener):
            response.geturl.return_value = 'https://www.facebook.com/reel/123/?mibextid=abc'
            self.assertEqual(server.resolve_share_url('https://fb.watch/abc/'), 'https://www.facebook.com/reel/123/')
            for target in ('https://facebook.com/login/', 'https://evil.test/reel/123/', 'https://fb.watch/abc/'):
                response.geturl.return_value = target
                with self.subTest(target=target), self.assertRaisesRegex(ValueError, '完整網址'):
                    server.resolve_share_url('https://fb.watch/abc/')


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()

    def setUp(self):
        server.JOBS.clear()
        self.worker = patch.object(server, 'worker').start()
        self.addCleanup(patch.stopall)

    def request(self, path, data=None, token=True, origin=None):
        headers = {'X-Access-Token': server.TOKEN} if token else {}
        if origin is not None: headers['Origin'] = origin
        body = json.dumps(data).encode() if data is not None else None
        if body is not None: headers['Content-Type'] = 'application/json'
        try:
            response = urlopen(Request(self.origin + path, data=body, headers=headers), timeout=5)
        except HTTPError as e:
            response = e
        with response:
            raw = response.read()
            value = json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw
            return response.status, value

    def test_authentication_and_origin_still_apply(self):
        self.assertEqual(self.request('/api/status', token=False)[0], 401)
        self.assertEqual(self.request('/api/prepare', {'url': 'https://instagram.com/reel/Chunk8-jurw/', 'format': 'mp4'}, token=False)[0], 401)
        self.assertEqual(self.request('/api/jobs', {}, origin='https://evil.test')[0], 403)

    def test_brand_assets_are_public_but_other_files_are_not(self):
        for path in server.STATIC_FILES:
            with self.subTest(path=path):
                status, body = self.request(path, token=False)
                self.assertEqual(status, 200)
                self.assertTrue(body)
        self.assertEqual(self.request('/server.py', token=False)[0], 401)
        self.assertEqual(self.request('/assets/../../server.py')[0], 404)

    def test_prepare_validates_without_starting_a_job(self):
        status, data = self.request('/api/prepare', {'url': 'https://instagram.com/reel/Chunk8-jurw/?igsh=abc', 'format': 'mp3'}, origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(data, {'url': 'https://www.instagram.com/reel/Chunk8-jurw/', 'platform': 'instagram', 'format': 'mp3'})
        self.assertFalse(server.JOBS)
        self.worker.assert_not_called()

    def test_job_platforms_queue_limit_and_cancel(self):
        for platform, url in [('youtube', 'https://youtu.be/jNQXAC9IVRw'), ('instagram', 'https://instagram.com/reel/Chunk8-jurw/'), ('facebook', 'https://facebook.com/reel/123/')]:
            status, data = self.request('/api/jobs', {'url': url, 'format': 'mp4', 'quality': '720'})
            self.assertEqual(status, 202)
            status, job = self.request('/api/jobs/' + data['id'])
            self.assertEqual(job['platform'], platform)
            self.assertNotIn('process', job)
            self.assertNotIn('file', job)
        self.assertEqual(self.request('/api/jobs', {'url': 'https://facebook.com/reel/456/', 'format': 'mp4'})[0], 429)
        self.assertEqual(self.request('/api/cancel/' + data['id'], {})[0], 200)
        self.assertEqual(server.JOBS[data['id']]['state'], 'cancelled')
        self.assertEqual(self.request('/api/jobs', {'url': 'https://facebook.com/reel/456/', 'format': 'mp4'})[0], 202)

    def test_rejects_invalid_urls_and_formats(self):
        for url, fmt in [('https://evil.test/video', 'mp4'), ('https://instagram.com/instagram/', 'mp4'), ('https://facebook.com/reel/123/', 'exe')]:
            with self.subTest(url=url, fmt=fmt):
                self.assertEqual(self.request('/api/jobs', {'url': url, 'format': fmt})[0], 400)
        self.assertFalse(server.JOBS)

    def test_ig_and_fb_do_not_require_youtube_javascript_runtime(self):
        with patch.object(server, 'NODE', None):
            self.assertEqual(self.request('/api/jobs', {'url': 'https://instagram.com/reel/Chunk8-jurw/', 'format': 'mp4'})[0], 202)
            self.assertEqual(self.request('/api/jobs', {'url': 'https://facebook.com/reel/123/', 'format': 'mp4'})[0], 202)
            self.assertEqual(self.request('/api/jobs', {'url': 'https://youtu.be/jNQXAC9IVRw', 'format': 'mp4'})[0], 400)

    def test_file_download_requires_completed_job_and_token(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / '影片.mp4'
            f.write_bytes(b'test media bytes')
            server.JOBS['test'] = {'state': 'running', 'file': str(f)}
            self.assertEqual(self.request('/files/test')[0], 404)
            server.JOBS['test']['state'] = 'done'
            self.assertEqual(self.request('/files/test', token=False)[0], 401)
            self.assertEqual(self.request('/files/test'), (200, b'test media bytes'))


class CloudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cloud_patch = patch.object(server, 'CLOUD', True)
        cls.cloud_patch.start()
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.http.server_port}'
        cls.origin = f'https://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.cloud_patch.stop()

    def setUp(self):
        server.JOBS.clear()
        self.cookie = 'mpdl_session=' + server.create_session()
        self.other_cookie = 'mpdl_session=' + server.create_session()
        self.worker_patch = patch.object(server, 'worker')
        self.worker_patch.start()
        self.addCleanup(self.worker_patch.stop)

    def request(self, path, body=None, cookie=None, origin=None):
        headers = {'Cookie': self.cookie if cookie is None else cookie}
        data = json.dumps(body).encode() if body is not None else None
        if data is not None:
            headers['Origin'] = self.origin if origin is None else origin
            headers['Content-Type'] = 'application/json'
        try:
            response = urlopen(Request(self.base + path, data=data, headers=headers), timeout=5)
        except HTTPError as e:
            response = e
        with response:
            raw = response.read()
            value = json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw
            return response.status, value, response.headers

    def test_homepage_creates_secure_browser_session(self):
        status, _, headers = self.request('/', cookie='')
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie']
        for flag in ('HttpOnly', 'Secure', 'SameSite=Strict', 'Max-Age=86400'):
            self.assertIn(flag, cookie)
        self.assertIsNotNone(server.read_session(cookie))
        self.assertEqual(self.request('/api/status', cookie=cookie)[0], 200)
        self.assertIsNone(self.request('/')[2].get('Set-Cookie'))

    def test_cloud_rejects_missing_tampered_and_expired_sessions(self):
        for cookie in ('', self.cookie[:-1] + ('a' if self.cookie[-1] != 'a' else 'b'), 'mpdl_session=' + server.create_session(now=0)):
            with self.subTest(cookie=cookie):
                self.assertEqual(self.request('/api/status', cookie=cookie)[0], 401)
        self.assertEqual(self.request('/api/status?token=' + server.TOKEN, cookie='')[0], 401)

    def test_https_origin_works_behind_proxy_without_trusting_forwarded_headers(self):
        body = {'url': 'https://instagram.com/reel/CDUMkliABpa/', 'format': 'mp4'}
        self.assertEqual(self.request('/api/prepare', body)[0], 200)
        for origin in ('https://evil.test', 'http://127.0.0.1:' + str(self.http.server_port), '', 'null'):
            with self.subTest(origin=origin):
                self.assertEqual(self.request('/api/prepare', body, origin=origin)[0], 403)

    def test_other_browser_cannot_read_cancel_or_download_a_job(self):
        status, created, _ = self.request('/api/jobs', {'url': 'https://facebook.com/reel/123/', 'format': 'mp4'})
        self.assertEqual(status, 202)
        jid = created['id']
        status, job, _ = self.request('/api/jobs/' + jid)
        self.assertEqual(status, 200)
        self.assertNotIn('owner', job)
        self.assertEqual(self.request('/api/jobs/' + jid, cookie=self.other_cookie)[0], 404)
        self.assertEqual(self.request('/api/cancel/' + jid, {}, cookie=self.other_cookie)[0], 404)
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / 'test.mp4'
            f.write_bytes(b'private media')
            server.JOBS[jid].update(state='done', file=str(f))
            self.assertEqual(self.request('/files/' + jid, cookie=self.other_cookie)[0], 404)
            self.assertEqual(self.request('/files/' + jid)[:2], (200, b'private media'))

    def test_status_does_not_expose_local_addresses_or_access_tokens(self):
        status, data, _ = self.request('/api/status')
        self.assertEqual(status, 200)
        self.assertEqual(data['mode'], 'cloud')
        self.assertEqual(data['local_url'], '')
        self.assertEqual(data['lan_url'], '')
        self.assertNotIn(server.TOKEN, json.dumps(data))

    def test_healthcheck_is_public_and_reports_missing_components(self):
        self.assertEqual(self.request('/healthz', cookie='')[0], 200)
        with patch.object(server, 'NODE', None):
            self.assertEqual(self.request('/healthz', cookie='')[:2], (503, {'ready': False}))

    def test_cleanup_only_removes_expired_completed_cloud_jobs(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'TUBEDROP_DOWNLOAD_DIR': folder}):
            old, active, recent = 'a' * 32, 'b' * 32, 'c' * 32
            for jid in (old, active, recent):
                (Path(folder)/jid).mkdir()
                (Path(folder)/jid/'file.mp4').write_bytes(b'media')
            server.JOBS.update({old: {'state': 'done', 'finished': 0}, active: {'state': 'running', 'created': 0}, recent: {'state': 'done', 'finished': 10000}})
            server.cleanup_expired(now=10001)
            self.assertNotIn(old, server.JOBS)
            self.assertFalse((Path(folder)/old).exists())
            self.assertTrue((Path(folder)/active/'file.mp4').is_file())
            self.assertTrue((Path(folder)/recent/'file.mp4').is_file())
            with patch.object(server, 'CLOUD', False):
                server.cleanup_expired(now=999999)
            self.assertIn(recent, server.JOBS)


class WorkerTests(unittest.TestCase):
    def test_successful_media_is_attached_to_the_correct_job(self):
        for platform in server.PLATFORMS:
            for fmt in ('mp4', 'mp3'):
                with self.subTest(platform=platform, fmt=fmt), tempfile.TemporaryDirectory() as folder:
                    jid = platform + fmt
                    output = Path(folder) / 'downloads' / jid / ('影片.' + fmt)
                    output.parent.mkdir(parents=True)
                    output.write_bytes(b'media')
                    job = dict(state='queued', url='https://example.test/video', platform=platform, format=fmt, quality='best')
                    process = Mock(stdout=io.StringIO(f'TITLE:影片\nPROGRESS:50%|1 MiB/s|1s\nFILE:{output}\n'))
                    process.wait.return_value = 0
                    with patch.object(server, 'ROOT', Path(folder)), patch.dict(server.JOBS, {jid: job}, clear=True), patch.object(server.subprocess, 'Popen', return_value=process):
                        server.worker(jid)
                    self.assertEqual(job['state'], 'done')
                    self.assertEqual(job['filename'], '影片.' + fmt)
                    self.assertEqual(job['size'], 5)
                    self.assertEqual(job['progress'], 100)

    def test_login_failure_has_readable_hint_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            job = dict(state='queued', url='https://instagram.com/reel/Chunk8-jurw/', platform='instagram', format='mp4', quality='best')
            process = Mock(stdout=io.StringIO('ERROR: [Instagram] Login required\n'))
            process.wait.return_value = 1
            with patch.object(server, 'ROOT', Path(folder)), patch.dict(server.JOBS, {'test': job}, clear=True), patch.object(server.subprocess, 'Popen', return_value=process):
                server.worker('test')
            self.assertEqual(job['state'], 'error')
            self.assertIn('登入', job['error'])
            self.assertIn('Login required', job['details'])

    def test_cancelled_queue_does_not_launch_downloader(self):
        with patch.dict(server.JOBS, {'test': {'state': 'cancelled'}}, clear=True), patch.object(server.subprocess, 'Popen') as popen:
            server.worker('test')
            popen.assert_not_called()

    def test_silent_video_explains_why_mp3_is_unavailable(self):
        hint = server.download_error('instagram', 'ERROR: Postprocessing: WARNING: unable to obtain file audio codec with ffprobe')
        self.assertIn('音軌', hint)
        self.assertIn('MP4', hint)


if __name__ == '__main__':
    unittest.main()
