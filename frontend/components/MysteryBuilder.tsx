"use client";

import { useEffect, useMemo, useState } from "react";
import {
  API_BASE,
  structureScenario,
  advanceMystery,
  askMysteryGM,
  createMysteryGame,
  getMysteryGame,
  importScenario,
  performMysteryAction,
  voteMystery,
} from "../lib/api";
import type { ImportedScenario, MysteryGame, ScenarioFormat } from "../lib/types";
import RealtimeRoom from "./RealtimeRoom";
import CampaignPanel from "./CampaignPanel";

const sample = `title: 雪山荘の惨劇
players: 3
characters:
  - id: doctor
    name: 片桐
    role: 医師
    secrets: [被害者に借金がある]
    objectives: [犯人を特定する]
  - id: writer
    name: 雪乃
    role: 作家
    secrets: [21時50分に書斎から怒鳴り声を聞いた]
    objectives: [山荘の評判を守る]
  - id: investor
    name: 千堂
    role: 投資家
    secrets: [あなたが犯人である]
    objectives: [最多票を避ける]
truth:
  culprit: investor
  crime_time: "22:15"
  crime_scene: 書斎
  weapon: ナイフ
evidence:
  - id: corpse
    title: 遺体
    content: 胸部に刺創がある。
  - id: diary
    title: 日記
    content: 千堂との契約トラブルが記されている。
phases:
  - id: opening
    label: 導入
    type: discussion
    duration: 5分
    start_evidence: [corpse]
    instructions: 自己紹介とアリバイを共有してください。
  - id: investigation
    label: 調査
    type: investigation
    duration: 15分
    instructions: 調べたい場所を選んでください。
  - id: voting
    label: 投票
    type: voting
    duration: 5分
    instructions: 最も怪しい人物へ投票してください。
events:
  - id: discover_diary
    trigger: {action: investigate, target: desk}
    conditions: {phase: investigation}
    result:
      unlock_evidence: [diary]
      message: 机の奥から日記を発見した。
endings:
  - id: true_end
    label: 真相解明
    condition: {type: culprit_votes_max}
    text: 真犯人を突き止めた。
  - id: bad_end
    label: 迷宮入り
    condition: {type: default}
    text: 真犯人は逃げ切った。
`;

export default function MysteryBuilder({ initialGameId }: { initialGameId?: string }) {
  const [rawText, setRawText] = useState(sample);
  const [prose, setProse] = useState("");
  const [previousResult, setPreviousResult] = useState("");
  const [structureMessage, setStructureMessage] = useState("");
  const [format, setFormat] = useState<ScenarioFormat>("yaml");
  const [scenario, setScenario] = useState<ImportedScenario | null>(null);
  const [game, setGame] = useState<MysteryGame | null>(null);
  const [seat, setSeat] = useState(1);
  const [aiCount, setAiCount] = useState(0);
  const [aiVisibility, setAiVisibility] = useState<"exact" | "range" | "hidden">("range");
  const [gmQuestion, setGmQuestion] = useState("次は何すればいい？");
  const [gmReply, setGmReply] = useState("");
  const [voteTarget, setVoteTarget] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!initialGameId) return;
    let disposed = false;
    setLoading(true);
    getMysteryGame(initialGameId, 1).then(next => {
      if (!disposed) setGame(next);
    }).catch(e => {
      if (!disposed) setError(e instanceof Error ? e.message : "セッションを読み込めませんでした。");
    }).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [initialGameId]);

  const report = scenario?.validation_report;
  const canStart = scenario?.status === "ready";
  const playerCount = scenario?.definition?.players ?? 0;

  const currentCharacter = game?.me;
  const targetOptions = useMemo(() => game?.players ?? [], [game]);

  function changeDraft(text: string) {
    setRawText(text); setScenario(null); setGame(null);
  }

  function downloadDraft() {
    const blob = new Blob([rawText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url;
    a.download = `scenario.${format === "markdown" ? "md" : format}`;
    a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function loadCampaignSample() {
    setLoading(true); setError("");
    try {
      const responses = await Promise.all([fetch(`${API_BASE}/scenarios/sample/`), fetch(`${API_BASE}/scenarios/sample/?kind=result`)]);
      if (responses.some(r => !r.ok)) throw new Error("サンプルを読み込めませんでした。");
      changeDraft(await responses[0].text()); setFormat("yaml");
      setPreviousResult(await responses[1].text()); setAiCount(0);
    } catch (e) { setError(e instanceof Error ? e.message : "読込に失敗しました。"); }
    finally { setLoading(false); }
  }

  async function handleStructure() {
    setLoading(true); setError(""); setStructureMessage("");
    try {
      const result = await structureScenario(prose);
      changeDraft(result.yaml); setFormat("yaml");
      setStructureMessage(result.validation_report.valid ? "YAMLに構造化しました。内容を確認し、解析・設定チェックから取り込んでください。" : "YAMLを生成しましたが修正が必要です。解析・設定チェックで詳細を確認してください。");
    } catch (e) { setError(e instanceof Error ? e.message : "構造化に失敗しました。"); }
    finally { setLoading(false); }
  }

  async function loadFile(file: File) {
    const text = await file.text();
    changeDraft(text);
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext === "json") setFormat("json");
    else if (ext === "md" || ext === "txt") setFormat("markdown");
    else setFormat("yaml");
  }

  async function handleImport() {
    setLoading(true);
    setError("");
    setGame(null);
    try {
      const imported = await importScenario(rawText, format);
      setScenario(imported);
      setAiCount(imported.definition?.campaign ? 0 : Math.min(1, imported.definition?.players ?? 0));
    } catch (e) {
      setError(e instanceof Error ? e.message : "シナリオを読み込めませんでした。");
    } finally {
      setLoading(false);
    }
  }

  async function handleStart() {
    if (!scenario) return;
    setLoading(true);
    setError("");
    try {
      const created = await createMysteryGame(scenario.id, aiCount, aiVisibility, scenario.definition?.campaign ? JSON.parse(previousResult) : undefined);
      const privateView = await getMysteryGame(created.id, 1);
      setSeat(1);
      setGame(privateView);
      setVoteTarget(privateView.players[0]?.character_id ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "ゲームを開始できませんでした。");
    } finally {
      setLoading(false);
    }
  }

  async function refreshForSeat(nextSeat: number) {
    if (!game) return;
    setLoading(true); setError("");
    try {
      const updated = await getMysteryGame(game.id, nextSeat);
      setSeat(nextSeat); setGame(updated); setGmReply("");
    } catch (e) { setError(e instanceof Error ? e.message : "座席を読み込めませんでした。"); }
    finally { setLoading(false); }
  }

  async function handleAdvance() {
    if (!game) return;
    const updated = await advanceMystery(game.id, seat);
    setGame(updated);
  }

  async function handleInvestigateDesk() {
    if (!game) return;
    const response = await performMysteryAction(game.id, seat, "investigate", "desk");
    setGame(response.game);
  }

  async function handleAskGM() {
    if (!game) return;
    const response = await askMysteryGM(game.id, seat, gmQuestion);
    setGmReply(response.text);
  }

  async function handleVote() {
    if (!game || !voteTarget) return;
    const updated = await voteMystery(game.id, seat, voteTarget);
    setGame(updated);
  }

  return (
    <div className="embeddedApp">
      {initialGameId && loading && <p>セッションを読み込み中…</p>}
      {initialGameId && error && <pre className="error">{error}</pre>}
      {!initialGameId && <>
      <section className="panel">
        <div className="sectionHead">
          <div><span>01</span><h2>シナリオ読込</h2></div>
          <p>自然文からYAMLを生成し、編集・検証して取り込めます。</p>
        </div>

        <p>作者用のサンプルには真相と個別情報が含まれます。</p>
        <div className="inlineFields">
          <a className="ghost" href={`${API_BASE}/scenarios/sample/`}>9人用サンプルをDL（YAML）</a>
          <a className="ghost" href={`${API_BASE}/scenarios/sample/?kind=result`}>人狼の結果の入力例をDL</a>
          <button className="ghost" disabled={loading} onClick={loadCampaignSample}>9人用サンプルを読み込む</button>
        </div>
        <label className="field">自然文のシナリオ・ルール
          <textarea value={prose} onChange={e => setProse(e.target.value)} placeholder="舞台、登場人物、事件の真相、会議数、カードの内容や取得条件を書いてください。" rows={6} />
        </label>
        <p className="muted">AI構造化を実行すると、この文章をサーバーに設定されたAIへ送信します。生成後は内容を確認できます。</p>
        <button className="ghost" disabled={loading || !prose.trim()} onClick={handleStructure}>{loading ? "処理中…" : "AIでYAMLを生成"}</button>
        {structureMessage && <p>{structureMessage}</p>}
        <div className="mysteryImportGrid">
          <div>
            <div className="inlineFields">
              <label className="field">形式
                <select value={format} onChange={(e) => setFormat(e.target.value as ScenarioFormat)}>
                  <option value="yaml">YAML</option>
                  <option value="json">JSON</option>
                  <option value="markdown">Markdown / txt</option>
                </select>
              </label>
              <label className="field fileField">ファイル
                <input type="file" accept=".yaml,.yml,.json,.md,.txt" onChange={(e) => e.target.files?.[0] && loadFile(e.target.files[0])} />
              </label>
            </div>
            <textarea className="scenarioText" value={rawText} onChange={(e) => changeDraft(e.target.value)} spellCheck={false} />
            <button className="ghost" onClick={downloadDraft}>編集中のシナリオをDL</button>
            <button className="primary wideButton" disabled={loading} onClick={handleImport}>解析・設定チェック</button>
          </div>

          <div className="validationBox">
            <h3>検証結果</h3>
            {!report && <p className="muted">まだ解析していない。</p>}
            {report && (
              <>
                <div className={report.valid ? "statusBadge success" : "statusBadge danger"}>
                  {report.valid ? "ゲーム開始可能" : "修正が必要"}
                </div>
                <div className="tags">
                  {Object.entries(report.summary).map(([key, value]) => <span key={key}>{key}: {value}</span>)}
                </div>
                {report.errors.map((issue) => <div className="issue errorIssue" key={issue.code + issue.path}><b>{issue.code}</b><span>{issue.message}</span></div>)}
                {report.warnings.map((issue) => <div className="issue warningIssue" key={issue.code + issue.path}><b>{issue.code}</b><span>{issue.message}</span></div>)}
              </>
            )}
          </div>
        </div>
        {error && <pre className="error">{error}</pre>}
      </section>

      {scenario && (
        <section className="panel">
          <div className="sectionHead"><div><span>02</span><h2>セッション作成</h2></div><p>{scenario.title}</p></div>
          <div className="inlineFields">
            <label className="field">AI参加人数
              <input type="number" min={0} max={playerCount} value={aiCount} onChange={(e) => setAiCount(Number(e.target.value))} />
            </label>
            <label className="field">AI人数の公開
              <select value={aiVisibility} onChange={(e) => setAiVisibility(e.target.value as typeof aiVisibility)}>
                <option value="exact">正確に公開</option>
                <option value="range">範囲のみ</option>
                <option value="hidden">完全非公開</option>
              </select>
            </label>
            <div className="field"><span>人数</span><div className="staticField">{playerCount}人</div></div>
          </div>
          {scenario.definition?.campaign && <details><summary>単体テスト用：前の人狼の結果を指定</summary><label className="field">前の人狼の結果（JSON）
            <p>入力例の名前・役職・生死・勝利陣営を実際の結果に差し替えてください。キャラクターは役職とは独立して割り当てられます。</p>
            <input type="file" accept=".json" onChange={async e => { const file = e.target.files?.[0]; if (file) setPreviousResult(await file.text()); }} />
            <textarea rows={12} value={previousResult} onChange={e => setPreviousResult(e.target.value)} />
          </label></details>}
          <button className="primary wideButton" disabled={!canStart || loading} onClick={handleStart}>
            {canStart ? "GMレス・セッション開始" : "エラーを直すまで開始できない"}
          </button>
        </section>
      )}

      </>}

      {game && (
        <section className="panel">
          <div className="sectionHead"><div><span>03</span><h2>ゲーム進行</h2></div><p>{game.ai_presence_hint}</p></div>
          {!initialGameId && <p><a href={`/mystery/${game.id}`}>このマダミスの参加画面を開く</a></p>}
          <div className="sessionToolbar">
            <label className="field">自分の座席
              <select disabled={loading} value={seat} onChange={(e) => refreshForSeat(Number(e.target.value))}>
                {game.players.map((player) => <option key={player.seat} value={player.seat}>Seat {player.seat} / {player.display_name}</option>)}
              </select>
            </label>
            <div className="phaseCard">
              <small>Current Phase</small>
              <strong>{game.phase?.label ?? "終了"}</strong>
              <span>{game.phase?.instructions}</span>
            </div>
          </div>

          <RealtimeRoom<MysteryGame>
            key={`${game.id}:${seat}`}
            gameId={game.id}
            seat={seat}
            onGameSnapshot={(nextGame) => setGame(nextGame)}
          />

          {currentCharacter && (
            <div className="privateCard">
              <p className="eyebrow">PRIVATE / SEAT {seat}</p>
              <h3>{currentCharacter.character_name} <small>{currentCharacter.role}</small></h3>
              <div className="privateColumns">
                <div><b>秘密</b>{currentCharacter.secrets.map((x) => <p key={x}>{x}</p>)}</div>
                <div><b>目的</b>{currentCharacter.objectives.map((x) => <p key={x}>{x}</p>)}</div>
              </div>
            </div>
          )}

          <div className="evidenceGrid">
            {game.evidence.map((item) => <article key={item.id}><small>EVIDENCE</small><h3>{item.title}</h3><p>{item.content}</p></article>)}
          </div>

          {game.campaign && <CampaignPanel key={`${game.id}:${seat}:${game.phase?.id}`} game={game} seat={seat} onChange={setGame} />}

          {!game.finished && !game.campaign && (
            <div className="gameControls">
              <button className="ghost" onClick={handleAdvance}>次のフェーズへ</button>
              <button className="ghost" onClick={handleInvestigateDesk}>机を調べる</button>
              <div className="gmAsk">
                <input value={gmQuestion} onChange={(e) => setGmQuestion(e.target.value)} />
                <button className="ghost" onClick={handleAskGM}>GMに聞く</button>
              </div>
              <div className="voteBox">
                <select value={voteTarget} onChange={(e) => setVoteTarget(e.target.value)}>
                  {targetOptions.map((player) => <option key={player.character_id} value={player.character_id}>{player.character_name}</option>)}
                </select>
                <button className="primary" onClick={handleVote}>この人物に投票</button>
              </div>
            </div>
          )}

          {gmReply && <div className="gmReply"><b>AI GM</b><p>{gmReply}</p></div>}

          {game.finished && game.resolution && (
            <div className="endingCard">
              <p className="eyebrow">ENDING</p>
              <h2>{game.resolution.label}</h2>
              <p>{game.resolution.text}</p>
              <code>culprit: {String(game.resolution.truth.culprit ?? "")}</code>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
