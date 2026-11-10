FROM node:24-bookworm-slim AS javascript
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates libstdc++6 libatomic1 && rm -rf /var/lib/apt/lists/*
COPY --from=javascript /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY TubeDrop/ /app/TubeDrop/
COPY scripts/install_downloader.py /app/scripts/install_downloader.py
RUN python scripts/install_downloader.py && node --version && ffmpeg -version >/dev/null && useradd --system --uid 10001 --create-home mpdl

ENV PYTHONUNBUFFERED=1 \
    TUBEDROP_MODE=cloud \
    TUBEDROP_PYTHON=/usr/local/bin/python \
    TUBEDROP_DOWNLOAD_DIR=/tmp/mpdl-downloads \
    PORT=8080
USER mpdl
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD ["python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/healthz',timeout=3).read()"]
CMD ["python", "TubeDrop/server.py"]
