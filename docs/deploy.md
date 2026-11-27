# 社内サーバーへの公開手順(Docker)

社内のサーバー(Linux 推奨。Docker が動けば Windows / Mac でも可)に置いて、社員がブラウザから使えるようにする手順です。

## 構成

```
社員のブラウザ ──HTTPS──> リバースプロキシ(Caddy など) ──> アプリ(Docker・127.0.0.1:8001)
                                                          └ データ(Dockerのボリューム app_data)
```

- アプリのポートは **サーバー自身の中(127.0.0.1)にだけ** 開きます。社内への公開はリバースプロキシ(HTTPS)経由で行います。
- ワーカーは1つで動かします(SQLite を使うため。数十人規模の社内利用なら十分です)。

## 1. 準備(初回だけ)

1. サーバーに Docker と Docker Compose をインストールします。
2. このフォルダをサーバーに置きます(`git clone` またはコピー)。
3. 設定ファイルを作ります。

   ```bash
   cp .env.example .env
   ```

4. `.env` を開いて次を設定します。
   - `OPENAI_API_KEY` … OpenAI のAPIキー
   - `COOKIE_SECURE=true` … HTTPS で公開するとき必須です(ログイン情報を暗号化した通信でだけ送る設定)
   - 保存先(`DATA_DIR` など)は、Docker では `docker-compose.yml` で固定されるため変更不要です。

## 2. 起動

```bash
docker compose up -d --build
docker compose ps          # STATUS が healthy になれば成功
curl http://127.0.0.1:8001/health
```

## 3. 最初の管理者を作る(初回だけ)

```bash
docker compose run --rm app python -m app.create_admin
```

## 4. HTTPS で公開する(Caddy の例)

Caddy は証明書を自動で取得・更新してくれます。社内の独自ドメイン(例: `manual.example.co.jp`)をサーバーに向けたうえで、`Caddyfile` を作ります。

```
manual.example.co.jp {
    reverse_proxy 127.0.0.1:8001
}
```

Caddy を `caddy run` などで起動すれば、https://manual.example.co.jp/ で使えます(nginx など他のリバースプロキシでも、同じ向き先に転送すれば構いません)。

社内だけで使い、HTTPS が不要な場合は、リバースプロキシなしで `127.0.0.1:8001` に接続できる端末からのみ使えます。その場合は `COOKIE_SECURE=false` にしてください(true だとログインできません)。

> **注意**: `docker-compose.yml` の `FORWARDED_ALLOW_IPS: "*"` は、リバースプロキシが付けるIPアドレスの情報を信用する設定です。ポートを `0.0.0.0` に公開し直すと偽装される恐れがあるので、`127.0.0.1` のままにしてください。

## 5. 日々の運用

| やりたいこと | コマンド・操作 |
|---|---|
| ログを見る | `docker compose logs -f app` |
| 停止 / 再開 | `docker compose stop` / `docker compose start` |
| アプリを更新する | `git pull` してから `docker compose up -d --build`(データは残ります) |
| バックアップ | 管理者でログインし、「バックアップ」タブからZIPをダウンロード(定期的に、別の場所へ保管) |
| 復元 | 下記 |

### 復元

```bash
docker compose stop
docker compose run --rm -v "$PWD/backup-20261128-120000.zip:/tmp/backup.zip:ro" app python -m app.restore_backup /tmp/backup.zip
docker compose start
```

今あるデータは `before-restore-日時` という名前でボリューム内に残ります。

### データの場所

データは Docker のボリューム `app_data` にあります(`docker volume inspect` で確認できます)。`docker compose down -v` を実行するとデータごと消えるので、**`-v` は付けないでください**。

## 公開前のチェックリスト

- [ ] `.env` の `OPENAI_API_KEY` を設定した
- [ ] HTTPS で公開し、`COOKIE_SECURE=true` にした
- [ ] 管理者のパスワードは推測されにくいものにした(8文字以上。長いほど安全)
- [ ] 「バックアップ」タブからバックアップを取り、別の場所に保管した
- [ ] サーバーの外から `http://サーバー:8001` に直接つながらないことを確認した
- [ ] 試験用のユーザーを削除した
