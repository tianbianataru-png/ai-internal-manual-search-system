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
- 初期版にログイン・権限管理はありません(将来追加予定)。

## 使い方
1. `.env` に `OPENAI_API_KEY` を設定して起動します。
2. http://127.0.0.1:8001/ を開きます。
3. 「マニュアル管理」でPDF / Word / テキストを登録します。
4. 「質問する」で質問すると、登録マニュアルだけを根拠にした回答と出典が表示されます。
5. 「質問履歴」で過去の質問・回答・出典を確認・削除できます。

## API
自動生成のAPI仕様は http://127.0.0.1:8001/docs で確認できます。

| メソッド | パス | 内容 |
|---|---|---|
| POST | /api/manuals | マニュアル登録 |
| GET | /api/manuals | マニュアル一覧 |
| DELETE | /api/manuals/{id} | マニュアル削除 |
| POST | /api/ask | 質問(回答+出典) |
| GET | /api/history | 質問履歴の一覧 |
| GET | /api/history/{id} | 質問履歴の詳細 |
| DELETE | /api/history/{id} | 質問履歴の削除 |

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
