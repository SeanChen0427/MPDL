#!/usr/bin/env python3
"""Small LAN video download server. No third-party Python dependencies."""
import json, os, re, secrets, shutil, signal, socket, subprocess, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent
STATIC_FILES = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
    '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
    '/favicon.svg': ('favicon.svg', 'image/svg+xml'),
    '/assets/course-logo.jpg': ('assets/course-logo.jpg', 'image/jpeg'),
}
PORT = int(os.environ.get('TUBEDROP_PORT', '8765'))
TOKEN = secrets.token_urlsafe(24)
PYTHON = os.environ.get('TUBEDROP_PYTHON') or str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3')
if not Path(PYTHON).is_file():
    import sys
    PYTHON = shutil.which('python3.12') or shutil.which('python3.11') or shutil.which('python3.10') or sys.executable
FFMPEG = shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
NODE = shutil.which('node')
if not NODE:
    nodes = sorted((Path.home() / '.nvm/versions/node').glob('*/bin/node'))
    NODE = str(nodes[-1]) if nodes else None
JOBS = {}
LOCK = threading.RLock()
SLOT = threading.Semaphore(1)
PLATFORMS = {'youtube': 'YouTube', 'instagram': 'Instagram', 'facebook': 'Facebook'}

def platform_for_host(host):
    if host in ('youtu.be', 'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'):
        return 'youtube'
    if host in ('instagram.com', 'www.instagram.com', 'm.instagram.com'):
        return 'instagram'
    if host in ('facebook.com', 'www.facebook.com', 'm.facebook.com', 'mbasic.facebook.com',
                'web.facebook.com', 'touch.facebook.com', 'fb.watch', 'www.fb.watch') or re.fullmatch(r'[a-z]{2}-[a-z]{2}\.facebook\.com', host):
        return 'facebook'
    raise ValueError('目前支援 YouTube、Instagram（IG）與 Facebook（FB）的影片網址。')

def parse_video_url(raw):
    if not isinstance(raw, str) or len(raw) > 2048:
        raise ValueError('請貼上有效的影片網址。')
    raw = raw.strip()
    if any(c.isspace() or ord(c) < 32 or c == '\\' for c in raw):
        raise ValueError('網址不能包含空白或控制字元。')
    try:
        u = urlsplit(raw)
        if u.scheme not in ('http', 'https') or not u.hostname or u.username is not None or u.password is not None or u.port not in (None, 80, 443):
            raise ValueError()
    except ValueError:
        raise ValueError('請貼上 https:// 開頭的有效影片網址。') from None
    return u, platform_for_host(u.hostname.lower())

def normalize_url(raw):
    u, platform = parse_video_url(raw)
    path = u.path.rstrip('/') or '/'
    query = parse_qs(u.query, max_num_fields=50)
    if platform == 'youtube':
        if u.hostname.lower() == 'youtu.be':
            vid = path.lstrip('/')
        else:
            parts = path.lstrip('/').split('/')
            vid = query.get('v', [''])[0] if path == '/watch' else (parts[1] if len(parts) == 2 and parts[0] in ('shorts', 'live', 'embed') else '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
            raise ValueError('網址中沒有有效的 YouTube 影片 ID，請使用單支影片的分享網址。')
        return 'https://www.youtube.com/watch?v=' + vid
    if platform == 'instagram':
        match = re.fullmatch(r'/(?:(?!share/)[A-Za-z0-9_.]+/)?(p|tv|reels?)/([A-Za-z0-9_-]{1,64})(?:/embed)?', path)
        if not match or match[2] == 'audio':
            raise ValueError('請貼上 IG 單支 Reel 或影片貼文網址（/reel/、/p/、/tv/），不支援個人頁面、限時動態或音樂頁面。')
        kind = 'reel' if match[1] == 'reels' else match[1]
        return f'https://www.instagram.com/{kind}/{match[2]}/'

    # Preserve only content identifiers; discard tracking and redirect parameters.
    if u.hostname.lower() in ('fb.watch', 'www.fb.watch'):
        if re.fullmatch(r'/[A-Za-z0-9_-]{1,128}', path):
            return 'https://fb.watch' + path + '/'
    elif re.fullmatch(r'/share/[rvp]/[A-Za-z0-9_-]{1,128}', path):
        return 'https://www.facebook.com' + path + '/'
    elif re.fullmatch(r'/reel/[0-9]+', path):
        return 'https://www.facebook.com' + path + '/'
    elif path in ('/watch', '/watch/live', '/video.php', '/video/video.php', '/video/embed'):
        vid = query.get('v', query.get('video_id', ['']))[0]
        if re.fullmatch(r'[0-9]+', vid):
            return 'https://www.facebook.com/watch/?v=' + vid
    elif re.fullmatch(r'/[A-Za-z0-9_.-]+/videos/(?:[A-Za-z0-9_.-]+/)?[0-9]+', path):
        return 'https://www.facebook.com' + path + '/'
    elif re.fullmatch(r'/[A-Za-z0-9_.-]+/posts/(?:pfbid[A-Za-z0-9]+|[0-9]+)', path) or re.fullmatch(r'/groups/[A-Za-z0-9_.-]+/(?:posts|permalink)/(?:[0-9a-f]+/)?[0-9]+', path):
        return 'https://www.facebook.com' + path + '/'
    elif path in ('/story.php', '/permalink.php'):
        post_id, owner_id = query.get('story_fbid', [''])[0], query.get('id', [''])[0]
        if re.fullmatch(r'(?:pfbid[A-Za-z0-9]+|[0-9]+)', post_id) and (not owner_id or re.fullmatch(r'[0-9]+', owner_id)):
            params = {'story_fbid': post_id}
            if owner_id: params['id'] = owner_id
            return 'https://www.facebook.com' + path + '?' + urlencode(params)
    raise ValueError('請貼上 FB 單支影片、Reel、含影片的貼文或分享網址，不支援粉專首頁與相簿。')

def is_share_url(url):
    u = urlsplit(url)
    return u.hostname == 'fb.watch' or u.path.startswith('/share/')

class FacebookRedirectHandler(HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 2

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _, platform = parse_video_url(newurl)
        if platform != 'facebook':
            raise ValueError('分享網址導向其他網站，請改貼 Facebook 影片的完整網址。')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def resolve_share_url(url):
    if not is_share_url(url): return url
    # Resolve only Facebook links, checking every HTTP redirect before following it.
    opener = build_opener(FacebookRedirectHandler())
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'text/html'})
    try:
        with opener.open(req, timeout=15) as response:
            resolved = normalize_url(response.geturl())
        if is_share_url(resolved):
            raise ValueError('分享網址沒有提供可讀取的影片連結。')
        return resolved
    except (ValueError, HTTPError, URLError, OSError) as e:
        raise ValueError('無法展開 FB 分享網址。請在瀏覽器開啟影片，再複製 /reel/、/videos/ 或 /watch/?v= 的完整網址；需登入或私人影片目前無法下載。') from e

def download_error(platform, detail):
    name = PLATFORMS[platform]
    lower = detail.lower()
    if any(x in lower for x in ('unable to obtain file audio codec', 'no audio', 'does not contain any audio')):
        return '這支影片沒有可讀取的音軌，無法轉成 MP3。請改選 MP4，或使用含聲音的影片。'
    if any(x in lower for x in ('no video', 'no formats', 'does not contain any video')):
        return '這個貼文沒有可下載的影片，請確認不是純圖片貼文。'
    if any(x in lower for x in ('login', 'log in', 'sign in', 'private', 'cookies', 'registered users', 'rate-limit', 'rate limit', '429', '403', 'empty media response', 'bot')):
        return f'{name} 要求登入、限制存取或暫時限制下載。請確認影片可在未登入時公開播放，或稍後再試；目前不會讀取你的登入資料。'
    if any(x in lower for x in ('not available', 'unavailable', 'removed', '404')):
        return f'{name} 影片無法取得，可能已刪除、非公開或有地區限制。'
    if any(x in lower for x in ('timed out', 'unable to download', 'name resolution', 'nodename nor servname', 'network is unreachable')):
        return f'無法連上 {name}，請確認 Mac 的網路連線，稍後再試。'
    if 'requested format' in lower:
        return '來源沒有符合所選畫質的格式，請改選「最高可用畫質」；MP3 需要影片本身含有聲音。'
    return f'無法完成 {name} 下載。請確認網址含有公開影片；平台更新或存取限制也可能造成失敗。'

def update(jid, **changes):
    with LOCK:
        JOBS[jid].update(changes)

def command(url, fmt, quality, folder):
    args = [PYTHON, str(ROOT/'bin/yt-dlp'), '--ignore-config', '--no-playlist', '--playlist-items', '1', '--no-colors', '--newline', '--progress', '--socket-timeout', '25', '--retries', '3', '--fragment-retries', '3', '--abort-on-unavailable-fragments', '--no-overwrites', '--ffmpeg-location', str(Path(FFMPEG).parent), '-P', str(folder), '-o', '%(title).160B [%(id)s].%(ext)s', '--print', 'before_dl:TITLE:%(title)s', '--print', 'after_move:FILE:%(filepath)s', '--progress-template', 'download:PROGRESS:%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s', '--no-simulate']
    if NODE:
        args += ['--js-runtimes', 'node:' + NODE]
    if fmt == 'mp3':
        args += ['-f', 'ba/b', '-x', '--audio-format', 'mp3', '--audio-quality', '320K']
    else:
        cap = '' if quality == 'best' else '[height<=' + quality + ']'
        args += ['-f', f'bv*[ext=mp4]{cap}+ba[ext=m4a]/b[ext=mp4]{cap}/bv*{cap}+ba/b{cap}/bv{cap}', '--merge-output-format', 'mp4', '--remux-video', 'mp4']
    return args + ['--', url]

def worker(jid):
    with SLOT:
        with LOCK:
            job = JOBS[jid]
            if job['state'] == 'cancelled': return
            job['state'] = 'running'
        folder = ROOT/'downloads'/jid
        folder.mkdir(parents=True, exist_ok=True)
        log = []
        try:
            if is_share_url(job['url']):
                update(jid, message='正在解析 FB 分享網址…')
            url = resolve_share_url(job['url'])
            with LOCK:
                if job['state'] == 'cancelled': return
                update(jid, message='正在讀取影片…')
                p = subprocess.Popen(command(url, job['format'], job['quality'], folder), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', start_new_session=True)
                job['process'] = p
            for raw in p.stdout:
                line = raw.strip()
                log.append(line)
                log = log[-30:]
                if line.startswith('TITLE:'):
                    update(jid, title=line[6:])
                elif line.startswith('PROGRESS:'):
                    fields = line[9:].split('|')
                    try: percent = float(fields[0].strip().strip('%'))
                    except ValueError: percent = 0
                    update(jid, progress=max(0, min(100, percent)), message='正在下載 · ' + ' · '.join(x.strip() for x in fields))
                elif line.startswith('FILE:'):
                    f = Path(line[5:]).resolve()
                    if f.parent == folder.resolve(): update(jid, file=str(f), filename=f.name)
                elif line.startswith(('[Merger]', '[ExtractAudio]', '[VideoRemuxer]')):
                    update(jid, message='正在合併／轉檔，完成後即可儲存…', progress=100)
            code = p.wait()
            with LOCK:
                if job['state'] == 'cancelled': return
            if code != 0 or not job.get('file') or not Path(job['file']).is_file():
                errors = [x for x in log if 'ERROR:' in x]
                raise RuntimeError('\n'.join(errors[-3:] or log[-5:]) or '下載未完成，請稍後重試。')
            if Path(job['file']).suffix != '.' + job['format']:
                raise RuntimeError('轉檔格式與選擇不符，請重試。')
            update(jid, state='done', progress=100, message='檔案已準備好', size=Path(job['file']).stat().st_size)
        except Exception as e:
            with LOCK:
                if job['state'] != 'cancelled':
                    detail = str(e)[-4000:]
                    hint = str(e) if isinstance(e, ValueError) else download_error(job['platform'], detail)
                    update(jid, state='error', message='無法完成下載', error=hint, details=detail)
        finally:
            update(jid, process=None)

def public_job(job):
    return {k:v for k,v in job.items() if k not in ('process', 'file')}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass  # Access tokens must not appear in request logs.
    def send(self, status, data, mime='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, dict) else data
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(body)
    def authorized(self):
        supplied = self.headers.get('X-Access-Token') or parse_qs(urlsplit(self.path).query).get('token', [''])[0]
        return secrets.compare_digest(supplied, TOKEN)
    def do_GET(self):
        path = urlsplit(self.path).path
        if path in STATIC_FILES:
            filename, mime = STATIC_FILES[path]
            return self.send(200, (ROOT/'web'/filename).read_bytes(), mime)
        if not self.authorized(): return self.send(401, {'error':'請使用啟動視窗提供的完整網址開啟。'})
        if path == '/api/status':
            return self.send(200, {'ready': (ROOT/'bin/yt-dlp').is_file() and Path(FFMPEG).is_file(), 'youtube_ready': bool(NODE), 'local_url': LOCAL_URL, 'lan_url': LAN_URL, 'platforms': PLATFORMS})
        if path.startswith('/api/jobs/'):
            jid = path.split('/')[-1]
            with LOCK:
                job = JOBS.get(jid)
                return self.send(200, public_job(job)) if job else self.send(404, {'error':'找不到這筆下載，可能已重新啟動。'})
        if path.startswith('/files/'):
            jid = path.split('/')[-1]
            with LOCK:
                job = JOBS.get(jid)
                f = Path(job['file']) if job and job['state'] == 'done' else None
            if not f or not f.is_file(): return self.send(404, {'error':'檔案尚未完成或已被移除。'})
            self.send_response(200)
            self.send_header('Content-Type', 'audio/mpeg' if f.suffix == '.mp3' else 'video/mp4')
            self.send_header('Content-Length', str(f.stat().st_size))
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(f.name))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                with f.open('rb') as data: shutil.copyfileobj(data, self.wfile, 1024*1024)
            except (BrokenPipeError, ConnectionResetError): pass
            return
        self.send(404, {'error':'找不到頁面'})
    def do_POST(self):
        if not self.authorized(): return self.send(401, {'error':'連線已失效，請重新開啟啟動視窗提供的網址。'})
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            return self.send(403, {'error':'不允許其他網站發起下載。'})
        path = urlsplit(self.path).path
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 1 or length > 4096: raise ValueError('請求內容不正確。')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict): raise ValueError('請求內容不正確。')
            if path in ('/api/jobs', '/api/prepare'):
                url = normalize_url(data.get('url'))
                platform = platform_for_host(urlsplit(url).hostname)
                fmt, quality = data.get('format'), data.get('quality', 'best')
                if fmt not in ('mp3','mp4') or quality not in ('best','2160','1440','1080','720'):
                    raise ValueError('請選擇有效的格式與畫質。')
                if path == '/api/prepare':
                    return self.send(200, {'url': url, 'platform': platform, 'format': fmt})
                if not (ROOT/'bin/yt-dlp').is_file() or not Path(FFMPEG).is_file():
                    raise ValueError('下載元件尚未就緒。')
                if platform == 'youtube' and not NODE:
                    raise ValueError('YouTube 下載需要 Node.js，請安裝後重新啟動；IG、FB 可繼續使用。')
                with LOCK:
                    if sum(j['state'] in ('queued','running') for j in JOBS.values()) >= 3:
                        return self.send(429, {'error':'目前已有 3 筆下載，請稍後再試。'})
                    jid = uuid.uuid4().hex
                    JOBS[jid] = dict(id=jid, url=url, platform=platform, format=fmt, quality=quality, state='queued', progress=0, title='正在讀取影片…', message='等待下載', created=time.time())
                threading.Thread(target=worker, args=(jid,), daemon=True).start()
                return self.send(202, {'id':jid})
            if path.startswith('/api/cancel/'):
                jid = path.split('/')[-1]
                with LOCK:
                    job = JOBS.get(jid)
                    if not job: return self.send(404, {'error':'找不到下載'})
                    if job['state'] in ('queued','running'):
                        job['state'], job['message'] = 'cancelled', '已取消下載'
                        p = job.get('process')
                        if p and p.poll() is None:
                            try: os.killpg(p.pid, signal.SIGTERM)
                            except ProcessLookupError: pass
                return self.send(200, {'ok':True})
            return self.send(404, {'error':'找不到頁面'})
        except (ValueError, TypeError) as e:
            return self.send(400, {'error':str(e)})

def lan_ip():
    for interface in ('en0','en1'):
        try:
            ip = subprocess.check_output(['/usr/sbin/ipconfig','getifaddr',interface], stderr=subprocess.DEVNULL, text=True).strip()
            if ip: return ip
        except (OSError, subprocess.CalledProcessError): pass
    return socket.gethostbyname(socket.gethostname())

LOCAL_URL = f'http://127.0.0.1:{PORT}/#token={TOKEN}'
try: LAN_URL = f'http://{lan_ip()}:{PORT}/#token={TOKEN}'
except OSError: LAN_URL = ''

if __name__ == '__main__':
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print('TubeDrop 已啟動。請保持這個視窗開啟。', flush=True)
    print('這台 Mac：' + LOCAL_URL, flush=True)
    print('同一 Wi-Fi：' + LAN_URL, flush=True)
    if os.environ.get('TUBEDROP_OPEN') == '1':
        import webbrowser
        webbrowser.open(LOCAL_URL)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        with LOCK:
            for job in JOBS.values():
                p = job.get('process')
                if p and p.poll() is None:
                    try: os.killpg(p.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
        server.server_close()
