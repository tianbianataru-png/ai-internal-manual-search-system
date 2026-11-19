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
uvicorn app.main:app --reload
```

ブラウザで http://127.0.0.1:8000/health を開き、`"status":"ok"` が出れば成功です。

## テスト

```powershell
pytest
```

## 注意
- `.env` と `data/` は Git に含めません(秘密情報・個人データのため)。
- 初期版にログイン・権限管理はありません(将来追加予定)。

## 開発状況
- [x] ステップ1: 環境構築
