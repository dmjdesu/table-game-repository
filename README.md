# AI Game Master MVP

AI人狼とGMレス・マーダーミステリーを、同じゲーム基盤の上で動かすためのMVPです。

## 設計方針

LLMにゲーム状態そのものを管理させません。

```text
Scenario / Rules
      ↓
Django Rule Engine
  ├─ Phase
  ├─ State
  ├─ Character
  ├─ Secret / Knowledge
  ├─ Evidence
  ├─ Action / Event
  ├─ Vote
  └─ Ending
      ↓
Visible State Filter
      ↓
AI GM / AI Player
      ↓
Next.js UI
```

ルール、秘密情報、証拠公開条件、投票、勝敗判定はDjango側で決定します。AIには「そのプレイヤーに見せてよい情報」だけを渡します。

## AI人狼

- 6 / 8 / 10人の公式プリセット
- 5〜15人のカスタム村
- 役職人数、初日占い、連続ガード、役欠け、再投票
- 人間・AI共通の発言回数制限
- AI人数・難易度・AI人数の公開方法
- AI席と役職を内部でランダム割り当て
- 公開APIではAI席・役職を秘匿
- 村構成を抽象状態に変換し、戦略キャッシュキーを生成

人狼戦略は完全一致の村構成ではなく、以下の特徴へ圧縮します。

- population_bucket
- wolf_pressure
- information_density
- protection_level
- deception_layer
- mislynch_budget

これにより変則村でも類似戦略を再利用できます。

## GMレス・マーダーミステリー

### シナリオ読込

対応形式:

- YAML
- JSON
- 構造化Markdown / txt
- Markdown内の fenced YAML / JSON

サンプル:

- `samples/yukiyama.yaml`
- `samples/structured-mystery.md`

シナリオを読み込むと以下を正規化します。

- characters
- secrets
- objectives
- truth
- evidence
- phases
- events
- endings

### 自動検証

開始前に最低限以下を検証します。

- プレイヤー数とキャラクター数
- 犯人が存在するか
- キャラクター / 証拠 / イベントIDの重複
- フェーズから未知の証拠を参照していないか
- イベントから未知の証拠を解放していないか
- フェーズが存在するか
- エンディングが存在するか
- 各キャラクターに秘密・目的があるか

エラーがあるシナリオはセッション開始できません。警告だけなら開始できます。

### セッション進行

現在のMVPで以下が動きます。

- キャラクターのランダム配布
- AI席の秘匿割り当て
- プレイヤーごとの秘密情報
- フェーズ進行
- フェーズ開始時の証拠公開
- `action + target` によるイベント発火
- 証拠アンロック
- 投票
- 全員投票後のエンディング判定
- 終了後のみ真相公開
- GMへの質問

AI GMは現在ルールベースの仮実装です。`GMProvider` インターフェースを用意しているので、OpenAI等のLLMに差し替え可能です。

重要なのは、LLMに `Scenario.definition` 全体を渡さないことです。`build_safe_gm_context` が公開情報と本人の個別情報だけを組み立てます。

## リアルタイムルーム

Django Channels + Redisで、人狼とマダミスが同じWebSocketルームを使います。

```text
Browser
  ↓ WebSocket
Daphne / Channels
  ↓
Redis Channel Layer
  ↓
Game Runtime
  ├─ phase timer
  ├─ speech AP
  ├─ chat
  └─ state broadcast
```

接続先:

```text
ws://localhost:8000/ws/games/<game_uuid>/?seat=1
```

主なWebSocketイベント:

- `snapshot`: 座席ごとにフィルタされたゲーム状態 + タイマー + AP + チャット履歴
- `chat.send`: 発言
- `chat.message`: 全員への発言配信
- `phase.advance`: Seat 1による暫定ホスト進行
- `state.refresh`: 状態再取得
- `error`: AP不足などの拒否

発言コストは、40文字以下=1AP、120文字以下=2AP、それ以上=3AP。人間とAIで同じ関数を通します。フェーズ変更時に全員のAPをリセットします。

人狼は `day_discussion → day_vote → night → 次の日` の共通時計を持ちます。マダミスはシナリオに定義した `duration_seconds` を使用します。タイムアウト時はChannels ConsumerがDBロックを取り、二重遷移を防ぎながら次フェーズへ進めます。

Docker ComposeではRedisとDaphneも同時に起動します。Redis未設定のCI・単体テストではInMemory Channel Layerへ自動フォールバックします。

## API

### 人狼

- `GET /api/presets/`
- `POST /api/config/validate/`
- `POST /api/strategy/preview/`
- `POST /api/games/`
- `GET /api/games/<uuid>/`

### シナリオ

- `POST /api/scenarios/import/`
- `GET /api/scenarios/<uuid>/`

保存済みシナリオの通常GETでは、真相や秘密を含むdefinitionを返しません。import直後のみ作者確認用として正規化definitionを返します。

### マダミス

- `POST /api/mystery/games/`
- `GET /api/mystery/games/<uuid>/?seat=1`
- `POST /api/mystery/games/<uuid>/advance/`
- `POST /api/mystery/games/<uuid>/actions/`
- `POST /api/mystery/games/<uuid>/vote/`
- `POST /api/mystery/games/<uuid>/gm/help/`

## 起動

### Docker

```bash
docker compose up
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000

### Backendのみ

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py test
python manage.py runserver
```

### Frontendのみ

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run lint
npm run build
npm run dev
```

## 次に載せるもの

1. LLM GM Provider
2. AIプレイヤーの戦略・会話・Humanization Layer
3. 自由文シナリオ → ScenarioDefinition 変換
4. 作者向けシナリオエディタ
5. 時間制イベント / 密談 / 個別チャット / アイテム交換
6. AIプレイヤーの長期記憶と人格
7. AI看破ポイント
8. 類似局面の戦略キャッシュ
9. 認証・ルーム招待・ホスト権限
10. TRPG / 脱出ゲーム用ルールモジュール

## 注意

商用マーダーミステリーの本文・キャラクター情報・真相等は著作物です。作者の許諾なく保存・公開・再配布する用途を前提にしないでください。まず自作・許諾作品向けとして運用する想定です。

また、このMVPには認証・権限管理がまだありません。本番化する際は作者APIとプレイヤーAPIを認証レベルでも分離してください。
