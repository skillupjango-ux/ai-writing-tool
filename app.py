"""AI ライティングツール（個人用）

起動:  uv run streamlit run app.py

設定（.env またはStreamlit Cloud の Secrets）:
  GEMINI_API_KEY  サーバー側で使う API キー（画面には一切表示しない）
  APP_PASSWORD    ログイン用パスワード。公開サーバーでは必須
  GEMINI_MODEL    既定モデル（任意）
"""

import hmac
import io
import mimetypes
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st
from docx import Document
from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import COMMON_SYSTEM, TOOLS, build_prompt

st.set_page_config(page_title="AI ライティングツール", page_icon="✍️", layout="wide")

# プロジェクト内の .env だけを読む（システムの環境変数は書き換えない）
load_dotenv(Path(__file__).parent / ".env")


def secret(name: str) -> str | None:
    """環境変数（.env）→ Streamlit Secrets の順に設定値を探す。"""
    if os.getenv(name):
        return os.getenv(name)
    try:
        return st.secrets.get(name) or None
    except Exception:  # secrets.toml が無い場合など
        return None


def is_local() -> bool:
    """自分の PC（localhost）から開いているか。"""
    host = (st.context.headers.get("Host") or "").rsplit(":", 1)[0]
    return host in ("localhost", "127.0.0.1", "[::1]")


SERVER_KEY = secret("GEMINI_API_KEY")
APP_PASSWORD = secret("APP_PASSWORD")
DEFAULT_MODEL = secret("GEMINI_MODEL") or "gemini-flash-latest"
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-pro-latest"]

MAX_UPLOAD_MB = 18  # Gemini にそのまま送れる合計サイズの目安（約20MB）
UPLOAD_TYPES = ["pdf", "png", "jpg", "jpeg", "webp", "docx", "txt", "md", "csv"]

REFINE_PRESETS = {
    "✂️ もっと短く": "全体をもっと短く、簡潔にしてください。",
    "🎩 もっと丁寧に": "もっと丁寧で、目上や社外の相手にも失礼のない表現にしてください。",
    "😊 柔らかく": "トーンをもう少し柔らかく、親しみやすくしてください。",
    "💪 はっきりと": "結論や依頼内容がよりはっきり伝わるようにしてください。",
    "📋 箇条書きで整理": "要点を箇条書きで整理して読みやすくしてください。",
    "🔄 別の言い回し": "内容は変えずに、別の言い回しで書き直してください。",
}

VARIANTS = [
    ("A 丁寧・しっかり", "丁寧さを一段上げ、背景説明や相手への配慮の言葉も十分に入れた、しっかりめの文章にする"),
    ("B バランス", "標準的な長さと丁寧さで、最も無難で使いやすい文章にする"),
    ("C 簡潔", "要点を絞り、できるだけ短く簡潔な文章にする"),
]


# ---------- ログイン ----------
if APP_PASSWORD and not st.session_state.get("authed"):
    st.title("✍️ AI ライティング")
    with st.form("login"):
        pw = st.text_input("パスワード", type="password")
        if st.form_submit_button("ログイン", type="primary"):
            if hmac.compare_digest(pw.encode(), APP_PASSWORD.encode()):
                st.session_state.authed = True
                st.rerun()
            time.sleep(2)  # 総当たり対策
            st.error("パスワードが違います。")
    st.stop()

# サーバーのキーを使ってよいのは「パスワードで守られている」か「自分の PC で動かしている」ときだけ
USE_SERVER_KEY = bool(SERVER_KEY) and (bool(APP_PASSWORD) or is_local())


# ---------- Gemini ----------
@st.cache_resource
def get_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


@st.cache_data(ttl=3600, show_spinner=False)
def list_models(api_key: str) -> list[str]:
    """API キーで使えるテキスト生成モデルの一覧を取得する。失敗したら固定リストを返す。"""
    try:
        names = [
            m.name.removeprefix("models/")
            for m in get_client(api_key).models.list()
            if "generateContent" in (m.supported_actions or [])
            and "gemini" in m.name
            and not any(x in m.name for x in ("image", "tts", "audio", "embedding", "live"))
        ]
        return sorted(set(names) | set(FALLBACK_MODELS))
    except Exception:
        return FALLBACK_MODELS


def gen_config(temperature: float) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(system_instruction=COMMON_SYSTEM, temperature=temperature)


def generate_stream(client: genai.Client, model: str, contents: list, temperature: float):
    """生成結果をストリーミングで1チャンクずつ返す。"""
    for chunk in client.models.generate_content_stream(
        model=model, contents=contents, config=gen_config(temperature)
    ):
        if chunk.text:
            yield chunk.text


def generate_parallel(client: genai.Client, model: str, contents_list: list, temperature: float) -> list[str]:
    """複数のプロンプトを同時に生成する（3案比較用）。"""
    with ThreadPoolExecutor(len(contents_list)) as ex:
        futures = [
            ex.submit(client.models.generate_content, model=model, contents=c, config=gen_config(temperature))
            for c in contents_list
        ]
        return [(f.result().text or "").strip() for f in futures]


def user_msg(text: str, file_parts: list | None = None) -> types.Content:
    return types.Content(role="user", parts=[*(file_parts or []), types.Part.from_text(text=text)])


def model_msg(text: str) -> types.Content:
    return types.Content(role="model", parts=[types.Part.from_text(text=text)])


def file_to_part(f) -> types.Part:
    """アップロードされたファイルを Gemini に渡せる形にする。"""
    ext = Path(f.name).suffix.lower()
    data = f.getvalue()
    if ext == ".docx":
        doc = Document(io.BytesIO(data))
        lines = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            lines += [" | ".join(c.text for c in row.cells) for row in table.rows]
        return types.Part.from_text(text=f"【添付ファイル: {f.name}】\n" + "\n".join(lines))
    if ext in (".txt", ".md", ".csv"):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("cp932", errors="replace")  # Windows の Shift_JIS
        return types.Part.from_text(text=f"【添付ファイル: {f.name}】\n{text}")
    mime = f.type or mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    return types.Part.from_bytes(data=data, mime_type=mime)  # PDF・画像は Gemini がそのまま読む


def last_text(conv: list) -> str:
    return conv[-1].parts[0].text


def add_history(tool_key: str, output: str, tag: str = "") -> None:
    st.session_state.setdefault("history", []).append(
        {"tool": tool_key, "output": output, "preview": tag + output.strip()[:15].replace("\n", " ") + "…"}
    )


def show_error(action: str, e: Exception) -> None:
    msg = str(e)
    if any(x in msg for x in ("503", "504", "UNAVAILABLE", "DEADLINE_EXCEEDED", "429", "RESOURCE_EXHAUSTED")):
        st.error(f"{action}に失敗しました（Gemini が混雑中か、利用上限に達しています）。"
                 "少し待つか、サイドバーの「⚙️ 設定」でモデルを lite などに変えて再実行してください。")
        st.caption(msg[:200])
    else:
        st.error(f"{action}に失敗しました: {msg}")


# ---------- サイドバー ----------
with st.sidebar:
    st.title("✍️ AI ライティング")
    tool_key = st.radio(
        "機能を選択",
        list(TOOLS),
        format_func=lambda k: TOOLS[k]["label"],
        label_visibility="collapsed",
    )

    st.divider()
    with st.expander("⚙️ 設定", expanded=not USE_SERVER_KEY):
        if USE_SERVER_KEY:
            api_key = SERVER_KEY  # 画面には出さない
            st.caption("🔑 サーバーに設定された API キーを使用中")
        else:
            api_key = st.text_input(
                "Gemini API キー",
                type="password",
                help="https://aistudio.google.com/apikey で取得できます",
            )
            if SERVER_KEY:
                st.caption("⚠️ 管理者へ: APP_PASSWORD が未設定のため、サーバーの API キーは使っていません")
        if api_key:
            models = list_models(api_key)
            model = st.selectbox(
                "モデル", models, index=models.index(DEFAULT_MODEL) if DEFAULT_MODEL in models else 0
            )
        else:
            model = DEFAULT_MODEL
        temperature = st.slider("創造性（高いほど自由な表現）", 0.0, 1.5, 0.7, 0.1)

    if APP_PASSWORD and st.button("ログアウト", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    if st.session_state.get("history"):
        st.divider()
        st.caption("🕘 履歴（この画面を開いている間だけ保持）")
        for h in reversed(st.session_state.history):
            with st.expander(f"{TOOLS[h['tool']]['label']}  {h['preview']}"):
                st.code(h["output"], language=None, wrap_lines=True)

# ---------- メイン ----------
tool = TOOLS[tool_key]
st.header(tool["label"])
st.caption(tool["desc"])

conv_key = f"conv_{tool_key}"  # 採用中の結果と修正のやりとり（Gemini への会話履歴）
variants_key = f"variants_{tool_key}"  # 3案比較の結果

col_in, col_out = st.columns(2, gap="large")

with col_in:
    with st.form(f"form_{tool_key}"):
        values = {}
        for f in tool["fields"]:
            wkey = f"{tool_key}_{f['key']}"
            if f["kind"] == "area":
                values[f["key"]] = st.text_area(
                    f["label"], height=f.get("height", 120), placeholder=f.get("placeholder", ""), key=wkey
                )
            elif f["kind"] == "text":
                values[f["key"]] = st.text_input(f["label"], placeholder=f.get("placeholder", ""), key=wkey)
            elif f["kind"] == "select":
                values[f["key"]] = st.selectbox(f["label"], f["options"], key=wkey)
        files = st.file_uploader(
            "📎 ファイル・画像を添付（任意）",
            type=UPLOAD_TYPES,
            accept_multiple_files=True,
            key=f"{tool_key}__files",
            help="PDF・Word・画像（スクショ）・テキストを読み込めます。合計 18MB まで",
        )
        extra = st.text_input(
            "追加の指示（任意）", placeholder="例：300字以内で / 箇条書きを使わないで",
            key=f"{tool_key}__extra",
        )
        compare = st.toggle("🅰️🅱️ 3パターン作って比較する", key=f"{tool_key}__compare")
        submitted = st.form_submit_button("✨ 作成する", type="primary", use_container_width=True)

with col_out:
    st.subheader("出力")

    # --- 新規作成 ---
    if submitted:
        first_field = tool["fields"][0]
        total_mb = sum(f.size for f in files) / 1024 / 1024
        if not api_key:
            st.error("サイドバーの「⚙️ 設定」で Gemini API キーを入力してください。")
        elif first_field["kind"] != "select" and not values[first_field["key"]].strip() and not files:
            st.warning(f"「{first_field['label']}」を入力するか、ファイルを添付してください。")
        elif total_mb > MAX_UPLOAD_MB:
            st.error(f"添付ファイルが大きすぎます（合計 {total_mb:.1f}MB / 上限 {MAX_UPLOAD_MB}MB）。")
        else:
            st.session_state.pop(conv_key, None)
            st.session_state.pop(variants_key, None)
            prompt = build_prompt(tool_key, values, extra)
            try:
                file_parts = [file_to_part(f) for f in files]
                if file_parts:
                    prompt += "\n# 添付ファイル\n添付したファイルの内容も入力情報として扱ってください。\n"
                client = get_client(api_key)
                if compare:
                    convs = [
                        [user_msg(prompt + f"\n# 今回の書き分け方針\n{direction}"
                                  "（入力で指定された丁寧さ・媒体などの条件は守ること）\n", file_parts)]
                        for _, direction in VARIANTS
                    ]
                    with st.spinner("3パターンを同時に作成中…"):
                        outputs = generate_parallel(client, model, convs, temperature)
                    st.session_state[variants_key] = [
                        {"label": label, "conv": conv + [model_msg(out)]}
                        for (label, _), conv, out in zip(VARIANTS, convs, outputs)
                    ]
                    for (label, _), out in zip(VARIANTS, outputs):
                        add_history(tool_key, out, f"[{label[0]}] ")
                else:
                    conv = [user_msg(prompt, file_parts)]
                    with st.container(border=True):
                        output = st.write_stream(generate_stream(client, model, conv, temperature))
                    st.session_state[conv_key] = conv + [model_msg(output)]
                    add_history(tool_key, output)
                st.rerun()  # 出力をコピー可能な表示に切り替える
            except Exception as e:
                show_error("生成", e)

    # --- 3案の比較表示 ---
    if variants_key in st.session_state:
        st.caption("タブで切り替えて比較できます。気に入った案は「この案で修正を続ける」で微調整できます")
        tabs = st.tabs([v["label"] for v in st.session_state[variants_key]])
        for i, (tab, v) in enumerate(zip(tabs, st.session_state[variants_key])):
            with tab:
                st.code(last_text(v["conv"]), language=None, wrap_lines=True)
                if st.button("✏️ この案で修正を続ける", key=f"adopt_{tool_key}_{i}"):
                    st.session_state[conv_key] = v["conv"]
                    del st.session_state[variants_key]
                    st.rerun()

    # --- 結果表示と追加修正 ---
    elif conv_key in st.session_state:
        conv = st.session_state[conv_key]
        rounds = (len(conv) - 2) // 2
        st.caption("右上のアイコンでコピーできます" + (f"（{rounds} 回修正済み）" if rounds else ""))
        st.code(last_text(conv), language=None, wrap_lines=True)

        st.markdown("**💬 さらに修正する**")
        instruction = None
        cols = st.columns(3)
        for i, (label, text) in enumerate(REFINE_PRESETS.items()):
            if cols[i % 3].button(label, key=f"preset_{tool_key}_{i}", use_container_width=True):
                instruction = text
        with st.form(f"refine_{tool_key}", clear_on_submit=True, border=False):
            c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
            free = c1.text_input("修正指示", placeholder="例：締め切りを金曜に変えて / 最後にお礼を一言",
                                 label_visibility="collapsed")
            if c2.form_submit_button("修正", use_container_width=True) and free.strip():
                instruction = free.strip()
        if rounds and st.button("↩️ 1つ前に戻す", key=f"undo_{tool_key}"):
            st.session_state[conv_key] = conv[:-2]
            st.rerun()

        if instruction:
            if not api_key:
                st.error("サイドバーの「⚙️ 設定」で Gemini API キーを入力してください。")
            else:
                new_conv = conv + [user_msg(
                    f"直前の文章を次の指示に従って修正し、修正後の全文だけを出力してください。\n指示: {instruction}"
                )]
                try:
                    with st.container(border=True):
                        output = st.write_stream(
                            generate_stream(get_client(api_key), model, new_conv, temperature)
                        )
                    st.session_state[conv_key] = new_conv + [model_msg(output)]
                    add_history(tool_key, output, "[修正] ")
                    st.rerun()
                except Exception as e:
                    show_error("修正", e)

    elif not submitted:
        st.info("左の欄に入力して「作成する」を押してください。")
