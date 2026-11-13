# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

個人用の AI ライティングツール（メール返信・要約・上長へのお伺い／報告・依頼・お詫び・校正・トーン変換・議事録・自由依頼）。
Python + Streamlit + Gemini API（`google-genai` SDK）。**データベース・ログイン認証は作らない方針**（個人用のため）。
履歴は `st.session_state` のみで、ファイルには保存しない。

## コマンド

```bash
uv sync                          # 依存パッケージをプロジェクト内 .venv に入れる
uv run streamlit run app.py      # 起動 → http://localhost:8501 を手で開く（headless 設定のため自動では開かない）
uv add <package>                 # 依存追加（pip は使わない）

# テストスイートは無い。変更後の最低限の確認:
uv run python -m py_compile app.py tools.py
uv run python -c "from tools import TOOLS, build_prompt; [build_prompt(k, {f['key']: 'x' for f in t['fields']}, '') for k, t in TOOLS.items()]"
```

`.streamlit/config.toml` で `headless = true` にしている。これが無いと初回起動時に Streamlit がメールアドレス入力で止まる（バックグラウンド起動も止まる）。
同ファイルの `address = "localhost"` で自分の PC からのみ接続可にしている（LAN・外部から `.env` の API キーを使われないため）。外さないこと。

必ず `uv run` を付けて起動する。`streamlit run app.py` だけだと Anaconda などグローバルの Python で動き、`google-genai` が無く ImportError になる。

## 構成

機能は **データ駆動**。`app.py` は機能ごとの分岐を持たず、`tools.py` の `TOOLS` 辞書から画面とプロンプトを組み立てる。

- `tools.py`
  - `TOOLS[key]` = `label` / `desc` / `fields` / `instruction`。`fields` の `kind` は `area` / `text` / `select`
  - `instruction` は `str.format` テンプレート。`{key}` が `fields` の `key` と一致している必要がある（不一致は実行時 KeyError）。`{}` を文字として書くときは `{{}}`
  - `build_prompt()` が空欄を「特になし」に置換し、「追加の指示」を末尾に「最優先」として付ける
  - `COMMON_SYSTEM` は全機能共通の system instruction（事実を創作しない／前置きを書かない 等）
- `app.py`
  - サイドバー: 機能選択・API キー・モデル・temperature・履歴
  - `list_models()` は API キーで使える Gemini モデルを `client.models.list()` から取得し（1時間キャッシュ）、失敗時は `FALLBACK_MODELS`。モデル名は時期で変わるためハードコードに頼らない
  - 生成は `generate_content_stream` → `st.write_stream`。完了後に結果を `session_state[f"result_{tool_key}"]` と `history` に保存して `st.rerun()` し、コピーボタン付きの `st.code` 表示に切り替える
  - 入力ウィジェットの key は `f"{tool_key}_{field_key}"` なので、機能を切り替えても入力内容が残る
  - 入力チェックは `fields` の先頭項目が空かどうかだけ（select 以外）。必須項目は先頭に置く

## 設定

- `.env`（Git 管理外）: `GEMINI_API_KEY`、任意で `GEMINI_MODEL`（既定 `gemini-flash-latest`）。雛形は `.env.example`
- `.env` はプロジェクト内のものだけを `load_dotenv(Path(__file__).parent / ".env")` で読む
- API キーは画面のサイドバーからも入力可能

## 削除（アンインストール）方法

このフォルダを丸ごと削除すれば完了。プロジェクト外には何もインストール・変更していない。
（uv のダウンロードキャッシュも消したい場合のみ `uv cache clean`。他の uv プロジェクトのキャッシュも消える点に注意）
