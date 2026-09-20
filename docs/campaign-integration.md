# 可変シナリオのマダミス

マダミスの作者画面・進行エンジン・参加画面を実装済み。人狼の設定・決着画面への接続はローカル版人狼のpush後に行う。既存の人狼の勝敗処理は変更していない。

## 実装済み

- `campaign.rounds` に会議のお題、選択肢、正答、配点、会議後のカード取得ルールを定義。議論→会議→取得のフェーズを生成する。
- 会議数、人数、カード枚数・内容、議論時間、陣営・役職対応、取得対象、1人あたり取得枚数、キャラクター固有のカード解釈を可変化。
- `draw.eligible`: `all` / `previous_winners` / 陣営ID。`per_player`: 取得枚数。draw省略時は取得なし。
- カードの内容は取得者のみ。会議回答は陣営内のみ。正誤と得点は最終会議後に公開。回答・取得完了前の進行をブロック。
- 結果入力の境界は `create_mystery_game(..., previous_result=...)`。座席、名前、役職、生死、勝利陣営を受け取り、人物を役職から独立して割り当てる。任意のcharacter_id指定で前ゲームの人物を維持できる。
- 9人・3会議・15カードのサンプル。KUNは被害者にしない。被害者と犯人は架空のNPC。死亡席も代理人として参加。
- 作者画面で自然文→AI→構造化YAML→編集→検証→インポート。サンプルと編集中のデータをDL可能。
- LangGraphで構造化→検証→修正（生成は合計最大3回）。通常のYAML利用ではAI依存は不要。

## 単体で試す

1. 通常の手順でバックエンドとフロントエンドを起動する。
2. 「GMレス・マダミス」→「9人用サンプルを読み込む」→「解析・設定チェック」。
3. 必要なら「単体テスト用：前の人狼の結果を指定」を開き、入力例を変更する。AI人数は0にする。
4. セッションを開始し、参加画面のリンク `/mystery/<gameId>` を開く。この画面は作者用の本文・真相編集欄を表示しない。再読み込みも可能。
5. 座席を切り替えてテストできる。座席1が手動進行し、議論は設定時間で自動進行する（WebSocket接続中）。会議・調査は回答や取得が揃うまで待つ。

サンプルのDLボタンでYAML、入力例のDLボタンで前ゲームの結果JSON、編集中のシナリオをDLボタンで編集データを保存できる。取得したカードの共有は議論で行う。自動的に相手のカード内容が表示されることはない。

## YAMLで調整する項目

`backend/game/scenarios/neet_recording.yaml` が完全なサンプル。`characters`と`players`の人数を合わせる。役職は `campaign.role_teams` で陣営へ対応付け、キャラクターは別に割り当てる。

- `campaign.rounds`: 要素数が会議数。各要素に `id`, `label`, `discussion_seconds`, `questions` を指定。
- `discussion_instructions`, `meeting_instructions`: 進行文を上書き可能。時間0の議論は手動進行。
- `draw`: 会議後の取得条件。省略時はカード取得なし。`eligible` と `per_player` を設定。
- `max_evidence`: 1回の回答に提出できる根拠枚数。既定2。全カードを一括指定して根拠点を得る操作を防ぐ。
- `questions`: `options` の選択肢IDで `answer` を指定。`points` が正答点、`evidence_any` に含まれる取得済みカードを根拠に指定すると `evidence_points` を加算（回答が正しい場合のみ）。
- `cards`: 枚数上限15は固定しない。`id`, `title`, `target`, `content` を指定。`interpretations` は人物IDごとの補足で、その人物が自分でカードを取得した時のみ表示。
- `teams`, `role_teams`, `speech_ap_per_phase`, `successor_label`, `introduction`, `ending_text`: 陣営・発言枠・代理人の表記・導入・結末を設定。

カードは重複取得不可。人数と実際の勝利陣営から必要枚数を計算し、不足時は開始を拒否する。会議回答は最初の陣営代表者の確定で固定し、採点と相手の回答は終了後に公開する。同点の場合は同点の陣営を勝者として表示する。

## 接続API

`POST /api/mystery/games/` に `scenario_id`, `previous_result`, `ai_count: 0` を渡す。結果形式は `backend/game/scenarios/previous_result.example.json` を参照。人狼側からの接続時は、ユーザー入力ではなくサーバーの確定結果を渡す。

```python
from game.mystery import create_mystery_game

game = create_mystery_game(scenario, previous_result={
    "winner_team": "village",
    "source_label": "前の人狼",
    "players": [
        # 全座席を1から連番で指定。例は1席分のみ。
        {"seat": 1, "display_name": "KUN", "role": "villager", "alive": True},
    ],
})
# 全参加者を /mystery/<game.id> へ遷移させる。
```

プレイヤーに `character_id` を指定した場合は維持し、省略した場合だけ未割当の人物をランダムに選ぶ。死亡席にも秘密・形見の記録・取得権が引き継がれる。

参加中の操作は `POST /api/mystery/games/<id>/campaign/`:

```json
{"seat": 1, "action": "pick", "card_id": "card01"}
```

```json
{"seat": 1, "action": "submit", "answers": {"voice": "recording"}, "evidence": []}
```

`GET /api/mystery/games/<id>/?seat=1` とWebSocketは同じ公開範囲のデータを返す。観戦用の座席指定なしでは個別カード・陣営回答を返さない。採点結果は `campaign.results`。

## AI設定

```bash
pip install -r backend/requirements-ai.txt
export OPENAI_API_KEY='...'
export SCENARIO_AI_MODEL='利用するモデルID'
python backend/manage.py migrate
```

`SCENARIO_AI_MODEL`にはJSON出力に対応したモデルを設定する。APIキーはバックエンドだけで扱う。自然文を構造化するボタンでのみ外部モデルへ送信し、進行中のゲーム状態は送らない。実API呼び出しは未確認。LangGraphの修正ループはテスト用生成関数で検証した。

## 人狼側のコード取得後に接続すること

1. ローカル版人狼を取得し、既存の勝敗判定と状態形式を確認する。
2. 人狼の設定に「終了後にマダミスへ進む」を追加。オフの場合は人狼単体で終了。
3. 人狼の決着画面からマダミスへ遷移。勝者・陣営・生死・座席・名前をサーバーの確定結果から引き継ぐ。プレイヤーに再入力させない。
4. 接続テスト用のJSON結果入力は作者画面内の折りたたみ欄に配置済み。通常の参加者は決着画面から直接マダミスの参加URLへ進む。
5. 二重遷移を防ぎ、同じ人狼からは同じ継続セッションを返す。全参加者が同じセッションへ移動できるようにする。

旧版には人狼の投票・襲撃・勝敗確定の実装がなく、進行フェーズの循環だけがあるため、勝者判定を推測して追加していない。連動マダミスの自動AIプレイヤーも未実装で、現在はAI人数0が必要。

## 検証状況

- Djangoテスト26件成功（既存14件＋新規12件）。両陣営の勝利、死亡席の取得、取得重複拒否、秘密分離、可変人数・会議数・取得枚数、サンプル再インポート、AI修正上限を確認。
- フロントエンドのTypeScriptチェック・production build成功。
- 既存MVPの座席切替方式を継承しており、ユーザー認証による座席所有の検証は未実装。公開運用前は既存ローカル版の認証に接続する。

参考: [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)、[ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai)。
