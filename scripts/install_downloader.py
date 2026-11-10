"""Download the pinned official yt-dlp artifact and verify before installing."""
import hashlib
from pathlib import Path
import urllib.request

VERSION = '2026.08.19'
SHA256 = '1fa6733c37ea6fb51c99ad8fe785e7b7e5f3246c9b980230329d4fb72ed8d4d6'
TARGET = Path(__file__).resolve().parents[1] / 'TubeDrop/bin/yt-dlp'
if TARGET.is_file() and hashlib.sha256(TARGET.read_bytes()).hexdigest() == SHA256:
    print('yt-dlp verified:', VERSION)
else:
    with urllib.request.urlopen(f'https://github.com/yt-dlp/yt-dlp/releases/download/{VERSION}/yt-dlp', timeout=60) as response:
        data = response.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != SHA256:
        raise SystemExit('yt-dlp checksum mismatch; installation stopped')
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(data)
    print('yt-dlp installed and verified:', VERSION)
