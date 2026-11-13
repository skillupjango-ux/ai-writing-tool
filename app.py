"""AI ライティングツール（個人用）

起動:  uv run streamlit run app.py
"""

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import COMMON_SYSTEM, TOOLS, build_prompt

# プロジェクト内の .env だけを読む（システムの環境変数は書き換えない）
load_dotenv(Path(__file__).parent / ".env")

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-pro-latest"]

st.set_page_config(page_title="AI ライティングツール", page_icon="✍️", layout="wide")


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


def generate(api_key: str, model: str, prompt: str, temperature: float):
    """生成結果をストリーミングで1チャンクずつ返す。"""
    stream = get_client(api_key).models.generate_content_stream(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=COMMON_SYSTEM, temperature=temperature),
    )
    for chunk in stream:
        if chunk.text:
            yield chunk.text


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
    with st.expander("⚙️ 設定", expanded=not os.getenv("GEMINI_API_KEY")):
        api_key = st.text_input(
            "Gemini API キー",
            value=os.getenv("GEMINI_API_KEY", ""),
            type="password",
            help=".env に GEMINI_API_KEY を書いておくと毎回の入力が不要になります",
        )
        if api_key:
            models = list_models(api_key)
            model = st.selectbox(
                "モデル", models, index=models.index(DEFAULT_MODEL) if DEFAULT_MODEL in models else 0
            )
        else:
            model = DEFAULT_MODEL
        temperature = st.slider("創造性（高いほど自由な表現）", 0.0, 1.5, 0.7, 0.1)

    if st.session_state.get("history"):
        st.divider()
        st.caption("🕘 履歴（この画面を開いている間だけ保持）")
        for i, h in enumerate(reversed(st.session_state.history)):
            with st.expander(f"{TOOLS[h['tool']]['label']}  {h['preview']}"):
                st.code(h["output"], language=None, wrap_lines=True)

# ---------- メイン ----------
tool = TOOLS[tool_key]
st.header(tool["label"])
st.caption(tool["desc"])

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
        extra = st.text_input(
            "追加の指示（任意）", placeholder="例：300字以内で / 2パターン出して / 箇条書きを使わないで",
            key=f"{tool_key}__extra",
        )
        submitted = st.form_submit_button("✨ 作成する", type="primary", use_container_width=True)

with col_out:
    st.subheader("出力")
    result_key = f"result_{tool_key}"

    if submitted:
        first_field = tool["fields"][0]
        if not api_key:
            st.error("サイドバーの「⚙️ 設定」で Gemini API キーを入力してください。")
        elif first_field["kind"] != "select" and not values[first_field["key"]].strip():
            st.warning(f"「{first_field['label']}」を入力してください。")
        else:
            prompt = build_prompt(tool_key, values, extra)
            try:
                with st.container(border=True):
                    output = st.write_stream(generate(api_key, model, prompt, temperature))
                st.session_state[result_key] = output
                st.session_state.setdefault("history", []).append(
                    {"tool": tool_key, "output": output, "preview": output.strip()[:15].replace("\n", " ") + "…"}
                )
                st.rerun()  # 出力をコピー可能な表示に切り替える
            except Exception as e:
                st.error(f"生成に失敗しました: {e}")

    if result_key in st.session_state:
        st.caption("右上のアイコンでコピーできます")
        st.code(st.session_state[result_key], language=None, wrap_lines=True)
    elif not submitted:
        st.info("左の欄に入力して「作成する」を押してください。")
