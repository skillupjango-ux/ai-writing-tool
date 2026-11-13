"""ライティング機能の定義。

機能を追加したいときは TOOLS に辞書を1つ足すだけでOK。
  - fields: 入力欄の定義（kind は "area" / "text" / "select"）
  - instruction: AI への指示文。{キー} の部分に入力値が入る
"""

COMMON_SYSTEM = """あなたは日本のビジネス文書に精通した、優秀なライティングアシスタントです。
- 自然で読みやすい日本語で書く
- 敬語は正確に使い、過剰な二重敬語は避ける
- 入力に書かれていない事実（日付・数値・固有名詞など）は創作しない。必要なら【〇〇】のようなプレースホルダーにする
- 出力は完成した文章そのものを中心にし、前置き（「以下が文章です」など）は書かない
"""

TONES = ["標準的な丁寧さ", "かなり丁寧（目上・社外向け）", "やや柔らかめ", "簡潔・ビジネスライク", "カジュアル"]
MEDIA = ["メール", "チャット（Slack / Teams など）", "口頭で伝える用"]

TOOLS = {
    "mail_reply": {
        "label": "✉️ メール返信",
        "desc": "受け取ったメールへの返信文を作成します。",
        "fields": [
            {"key": "received", "label": "受信したメール", "kind": "area", "height": 200,
             "placeholder": "返信したいメールの本文を貼り付けてください"},
            {"key": "intent", "label": "返信の方向性・伝えたいこと", "kind": "area", "height": 100,
             "placeholder": "例：日程は承諾。ただし資料の締切は1日延ばしてほしい"},
            {"key": "relation", "label": "相手との関係", "kind": "select",
             "options": ["社外（取引先・お客様）", "社内（上司・目上）", "社内（同僚）", "社内（部下・後輩）"]},
            {"key": "tone", "label": "トーン", "kind": "select", "options": TONES},
        ],
        "instruction": """次のメールへの返信文を作成してください。

# 受信したメール
{received}

# 返信で伝えたいこと
{intent}

# 条件
- 相手との関係: {relation}
- トーン: {tone}
- 件名（Re: を含む）と本文を出力する
- 署名は【署名】とだけ書く
""",
    },
    "summary": {
        "label": "📝 要約",
        "desc": "長い文章・資料・スレッドを要約します。",
        "fields": [
            {"key": "text", "label": "要約したい文章", "kind": "area", "height": 280},
            {"key": "style", "label": "要約の形式", "kind": "select",
             "options": ["3行まとめ", "箇条書き（要点5つ程度）", "一文で", "詳細めの要約（見出し付き）"]},
            {"key": "focus", "label": "特に知りたい観点（任意）", "kind": "text",
             "placeholder": "例：自分がやるべきこと、期限、決定事項"},
        ],
        "instruction": """次の文章を要約してください。

# 文章
{text}

# 条件
- 形式: {style}
- 重視する観点: {focus}
- 元の文章にない情報は加えない
- 期限・担当・決定事項が含まれていれば必ず残す
""",
    },
    "ask_boss": {
        "label": "🙇 上長へのお伺い・相談",
        "desc": "承認依頼・判断の相談・許可取りの文章を作成します。",
        "fields": [
            {"key": "subject", "label": "何についてのお伺いか", "kind": "text",
             "placeholder": "例：来月の展示会への出展可否"},
            {"key": "background", "label": "背景・経緯", "kind": "area", "height": 120},
            {"key": "proposal", "label": "自分の案・選択肢", "kind": "area", "height": 120,
             "placeholder": "例：A案（出展する／費用30万円）を推奨。B案は見送り"},
            {"key": "deadline", "label": "いつまでに判断がほしいか", "kind": "text", "placeholder": "例：今週金曜まで"},
            {"key": "media", "label": "伝える手段", "kind": "select", "options": MEDIA},
        ],
        "instruction": """上長に判断・承認をお願いする文章を作成してください。

# お伺いの内容
{subject}

# 背景・経緯
{background}

# 自分の案・選択肢
{proposal}

# 回答期限
{deadline}

# 条件
- 伝える手段: {media}
- 冒頭で「何を判断してほしいか」を明確にする
- 上長が Yes / No ですぐ答えられる形にする（選択肢があれば推奨案と理由を添える）
- 上長の時間を奪わないよう簡潔にまとめる
""",
    },
    "report_boss": {
        "label": "📊 上長への報告",
        "desc": "進捗報告・完了報告・トラブル報告・日報を作成します。",
        "fields": [
            {"key": "kind", "label": "報告の種類", "kind": "select",
             "options": ["進捗報告", "完了報告", "トラブル・ミスの報告", "日報", "週報"]},
            {"key": "facts", "label": "報告したい内容（メモ書きでOK）", "kind": "area", "height": 200,
             "placeholder": "箇条書きや走り書きで大丈夫です"},
            {"key": "issues", "label": "課題・懸念点（任意）", "kind": "area", "height": 80},
            {"key": "next", "label": "今後の対応・次のアクション（任意）", "kind": "area", "height": 80},
            {"key": "media", "label": "伝える手段", "kind": "select", "options": MEDIA},
        ],
        "instruction": """上長への「{kind}」を作成してください。

# 報告内容（メモ）
{facts}

# 課題・懸念点
{issues}

# 今後の対応
{next}

# 条件
- 伝える手段: {media}
- 結論ファースト（最初に結論・現状を一言で）
- 事実と自分の意見・推測は分けて書く
- トラブル報告の場合は「発生事象・影響範囲・原因（判明していれば）・対応状況・再発防止」の順を意識する
- 上長に判断や支援をお願いしたい点があれば明記する
""",
    },
    "request": {
        "label": "🤝 依頼・お願い",
        "desc": "同僚や他部署、社外への依頼文を作成します。",
        "fields": [
            {"key": "target", "label": "依頼相手", "kind": "text", "placeholder": "例：経理部の田中さん"},
            {"key": "what", "label": "依頼したいこと", "kind": "area", "height": 120},
            {"key": "why", "label": "理由・背景（任意）", "kind": "area", "height": 80},
            {"key": "deadline", "label": "期限（任意）", "kind": "text"},
            {"key": "tone", "label": "トーン", "kind": "select", "options": TONES},
            {"key": "media", "label": "伝える手段", "kind": "select", "options": MEDIA},
        ],
        "instruction": """次の依頼文を作成してください。

# 依頼相手
{target}

# 依頼内容
{what}

# 理由・背景
{why}

# 期限
{deadline}

# 条件
- トーン: {tone}
- 伝える手段: {media}
- 相手が「何を・いつまでに・どうすればいいか」すぐ分かるようにする
- 相手への配慮の一言を入れる
""",
    },
    "apology": {
        "label": "🙏 お詫び",
        "desc": "ミスや遅延などのお詫び文を作成します。",
        "fields": [
            {"key": "what", "label": "何が起きたか", "kind": "area", "height": 120},
            {"key": "target", "label": "お詫びする相手", "kind": "select",
             "options": ["社外（取引先・お客様）", "社内（上司・目上）", "社内（同僚）"]},
            {"key": "action", "label": "対応・再発防止策（任意）", "kind": "area", "height": 100},
        ],
        "instruction": """次の件についてのお詫び文を作成してください。

# 起きたこと
{what}

# 相手
{target}

# 対応・再発防止策
{action}

# 条件
- 言い訳がましくならないよう、まず率直にお詫びする
- 現在の対応状況と今後の対策を明確にする
- 件名が必要な場合は件名も付ける
""",
    },
    "proofread": {
        "label": "🔍 校正・推敲",
        "desc": "誤字脱字・敬語の誤り・分かりにくい表現をチェックして直します。",
        "fields": [
            {"key": "text", "label": "チェックしたい文章", "kind": "area", "height": 250},
        ],
        "instruction": """次の文章を校正・推敲してください。

# 文章
{text}

# 出力形式
## 修正版
（修正した文章全体）

## 主な修正点
- 修正前 → 修正後（理由）を箇条書きで。修正がなければ「修正の必要はありません」
""",
    },
    "tone_change": {
        "label": "🎨 トーン変換・リライト",
        "desc": "文章の丁寧さや長さを変えて書き直します。",
        "fields": [
            {"key": "text", "label": "元の文章", "kind": "area", "height": 200},
            {"key": "target", "label": "どう変えるか", "kind": "select",
             "options": ["もっと丁寧に", "もっと柔らかく", "もっと簡潔に（短く）", "もっと分かりやすく",
                         "カジュアルに", "チャット向けに短く", "メール向けに整える"]},
        ],
        "instruction": """次の文章を「{target}」の方針で書き直してください。

# 元の文章
{text}

# 条件
- 元の文章の意味・事実は変えない
""",
    },
    "minutes": {
        "label": "🗒️ 議事録作成",
        "desc": "会議のメモから議事録を作成します。",
        "fields": [
            {"key": "meta", "label": "会議名・日時・参加者（任意）", "kind": "text"},
            {"key": "memo", "label": "会議メモ（走り書きでOK）", "kind": "area", "height": 280},
        ],
        "instruction": """次の会議メモから議事録を作成してください。

# 会議情報
{meta}

# メモ
{memo}

# 出力形式
## 会議概要（会議名・日時・参加者）
## 決定事項
## 議論の要点
## ToDo（担当・期限）
## 次回までの宿題・保留事項

- メモにない情報は創作せず、不明な担当や期限は【未定】とする
""",
    },
    "free": {
        "label": "💬 自由に依頼",
        "desc": "上記以外の文章作成を自由にお願いできます。",
        "fields": [
            {"key": "request", "label": "依頼内容", "kind": "area", "height": 250,
             "placeholder": "例：送別会の案内文を作って。日時は〇〇、場所は〇〇"},
        ],
        "instruction": "{request}",
    },
}


def build_prompt(tool_key: str, values: dict, extra: str) -> str:
    """入力値を指示文に埋め込んでプロンプトを作る。空欄は「特になし」にする。"""
    filled = {k: (v.strip() if isinstance(v, str) and v.strip() else "特になし") for k, v in values.items()}
    prompt = TOOLS[tool_key]["instruction"].format(**filled)
    if extra.strip():
        prompt += f"\n# 追加の指示（最優先）\n{extra.strip()}\n"
    return prompt
