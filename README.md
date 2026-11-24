# AI社内マニュアル検索システム

社内マニュアル(PDF / Word / テキスト)を登録し、自然な文章で質問すると、
マニュアルの内容だけに基づいて回答と根拠(出典)を返すシステムです(RAG方式)。

## 使用技術
Python 3.13 / FastAPI / OpenAI API / ChromaDB / SQLite / PyMuPDF / python-docx

## セットアップ(Windows PowerShell)

```powershell
# 1. 仮想環境を作る(最初の1回だけ)
python -m venv .venv

# 2. 仮想環境を有効にする(PowerShellを開くたびに)
.\.venv\Scripts\Activate.ps1

# 3. ライブラリを入れる
pip install -r requirements.txt

# 4. 設定ファイルを作る
copy .env.example .env
#    .env を開き、OPENAI_API_KEY に自分のキーを書く(ステップ5から必要)
```

## 最初の管理者を作る(初回だけ)

```powershell
python -m app.create_admin
```

ユーザー名とパスワード(8文字以上)を入力します。以降のユーザーは、管理者でログインして「ユーザー管理」から追加します。

## 起動

```powershell
uvicorn app.main:app --reload --port 8001
```

ブラウザで http://127.0.0.1:8001/health を開き、`"status":"ok"` が出れば成功です。
画面は http://127.0.0.1:8001/ から使えます。

## テスト

```powershell
pytest
```

## 注意
- `.env` と `data/` は Git に含めません(秘密情報・個人データのため)。
- HTTPS で公開する場合は `.env` の `COOKIE_SECURE=true` を設定してください。

## 使い方
1. `.env` に `OPENAI_API_KEY` を設定して起動します。
2. http://127.0.0.1:8001/ を開き、ログインします。
3. 管理者は「マニュアル」でPDF / Word / テキストを登録します(一般ユーザーは閲覧のみ。マニュアルは全員共通です)。
4. 「質問する」で質問すると、登録マニュアルだけを根拠にした回答と出典が表示されます。回答文の `[1]` などの番号は、出典の番号に対応します(回答に使われた資料だけが出典に出ます)。「検索対象」で特定のマニュアルだけに絞ることもできます。
5. 「質問履歴」で自分の過去の質問・回答・出典を確認・削除できます(他の人の履歴は見えません)。

| 権限 | できること |
|---|---|
| 管理者 | 質問・履歴、マニュアルの登録/削除、ユーザーの追加/削除/パスワード変更 |
| 一般 | 質問・自分の履歴、マニュアルの閲覧 |

パスワードは、ログイン後の「パスワード変更」タブから本人が変更できます(現在のパスワードが必要。他の端末のログインは無効になります)。

## API
自動生成のAPI仕様は http://127.0.0.1:8001/docs で確認できます。

| メソッド | パス | 内容 |
|---|---|---|
| POST | /api/auth/login | ログイン |
| POST | /api/auth/logout | ログアウト |
| GET | /api/auth/me | ログイン中のユーザー |
| PUT | /api/auth/password | 自分のパスワード変更 |
| GET/POST | /api/users | ユーザー一覧/追加(管理者) |
| PUT | /api/users/{id}/password | パスワード変更(管理者) |
| DELETE | /api/users/{id} | ユーザー削除(管理者) |
| POST | /api/manuals | マニュアル登録(管理者) |
| GET | /api/manuals | マニュアル一覧 |
| DELETE | /api/manuals/{id} | マニュアル削除(管理者) |
| POST | /api/ask | 質問(回答+出典) |
| GET | /api/history | 質問履歴の一覧 |
| GET | /api/history/{id} | 質問履歴の詳細 |
| DELETE | /api/history/{id} | 質問履歴の削除 |
| PUT | /api/history/{id}/rating | 回答の評価(`good` / `bad` / `null`で取り消し。本人のみ) |
| GET | /api/feedback/summary | 評価の集計と「役に立たなかった」回答の一覧(管理者) |

## 開発状況
- [x] ステップ1: 環境構築
- [x] ステップ2〜3: DB・文書解析(PDF / Word / テキスト)
- [x] ステップ4: 文章の分割(チャンク分割)
- [x] ステップ5: Embedding
- [x] ステップ6: マニュアル登録API
- [x] ステップ7: AI質問応答(RAG)
- [x] ステップ8: 質問履歴API
- [x] ステップ9: HTML画面
- [x] ステップ10: テスト・仕上げ
- [x] ステップ11: ログイン・権限管理
- [x] ステップ12: 検索・回答の改善(引用した出典だけを表示・マニュアルの絞り込み)
- [x] ステップ13: 自分のパスワード変更
