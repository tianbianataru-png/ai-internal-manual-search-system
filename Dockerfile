# AI社内マニュアル検索システム 用のイメージ
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先にライブラリだけ入れる(ソースを変えても再インストールされず、ビルドが速い)
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY frontend ./frontend

# 一般ユーザーで動かす。データの保存先 /app/data は、この所有者のまま名前付きボリュームに引き継がれる
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app/data
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=4).status == 200 else 1)"

# ワーカーは1つ(SQLite・ログイン失敗の記録を1プロセスで扱うため)。
# リバースプロキシ(HTTPS)の後ろで本当のIPアドレスを操作ログに残すため --proxy-headers を付ける
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers"]
