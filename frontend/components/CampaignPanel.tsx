"use client";
import { useState } from "react";
import { advanceMystery, campaignAction } from "../lib/api";
import type { MysteryGame } from "../lib/types";

export default function CampaignPanel({ game, seat, onChange }: { game: MysteryGame; seat: number; onChange: (game: MysteryGame) => void }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [evidence, setEvidence] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const c = game.campaign;
  if (!c) return null;
  const label = (id: string) => c.teams.find(t => t.id === id)?.label ?? id;
  async function run(action: () => Promise<MysteryGame>) {
    setBusy(true); setError("");
    try { onChange(await action()); }
    catch (e) { setError(e instanceof Error ? e.message : "操作に失敗しました。"); }
    finally { setBusy(false); }
  }
  return <div className="campaignPanel">
    <p>{c.introduction}</p>
    <p>所属：{c.team ? label(c.team) : "観戦"} ／ {c.identity} ／ 前の人狼の勝者：{label(c.previous_winner)}</p>
    <p>同じ陣営：{c.team_members.map(p => `${p.display_name}（座席${p.seat}）`).join("、")}</p>
    <p>会議 {c.rounds.findIndex(r => r.id === c.round_id) + 1} / {c.rounds.length}：{c.rounds.find(r => r.id === c.round_id)?.label}</p>
    {c.skill && <p><b>固有能力：</b>{c.skill}</p>}
    <h3>取得した情報カード</h3>
    <div className="evidenceGrid">{c.owned_cards.map(card => <article key={card.id}><small>{card.id} / 自分だけに表示</small><h3>{card.title}</h3><p>{card.content}</p>{card.interpretation && <p><b>固有能力：</b>{card.interpretation}</p>}</article>)}</div>
    {c.my_history.length > 0 && <details><summary>自陣営の確定した回答</summary>{c.my_history.map(r => <div key={r.round_id}><b>{r.label}</b>{r.answers.map(a => <p key={a.question}>{a.question}：{a.label}</p>)}<p>根拠：{r.evidence.join("、") || "なし"}</p></div>)}</details>}
    {!game.finished && <>
      {game.phase?.type === "card_draw" && <><h3>調査先を選択（残り{c.remaining_picks}枚）</h3><p>カードは全員で共有する山札です。一度取得されたカードは選べません。</p></>}
      <div className="evidenceGrid">{c.catalogue.map(card => <article key={card.id}><small>{card.id} / {card.target}</small><h3>{card.title}</h3><p>{card.taken ? "取得済み" : "未取得"}</p>{game.phase?.type === "card_draw" && <button className="ghost" disabled={busy || card.taken || c.remaining_picks === 0} onClick={() => run(() => campaignAction(game.id, seat, { action: "pick", card_id: card.id }))}>取得する</button>}</article>)}</div>
      {game.phase?.type === "meeting" && <div className="privateCard">
        <h3>陣営の回答</h3>
        <p>確定済み：{c.submitted_teams.map(label).join("、") || "なし"}。相手の回答と採点は終了後に公開されます。</p>
        {c.questions.map(q => <label className="field" key={q.id}>{q.prompt}（{q.points}点{q.evidence_points > 0 ? `＋根拠${q.evidence_points}点` : ""}）
          <select disabled={busy || !!c.my_submission} value={c.my_submission?.answers[q.id] ?? answers[q.id] ?? ""} onChange={e => setAnswers({ ...answers, [q.id]: e.target.value })}><option value="">選択してください</option>{q.options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}</select>
        </label>)}
        <p>根拠カード（最大{c.max_evidence}枚。他の参加者から共有された取得済みカードも指定できます）</p>
        {c.catalogue.filter(x => x.taken).map(card => <label key={card.id} style={{ display: "block" }}><input type="checkbox" disabled={busy || !!c.my_submission || (!evidence.includes(card.id) && evidence.length >= c.max_evidence)} checked={(c.my_submission?.evidence ?? evidence).includes(card.id)} onChange={e => setEvidence(e.target.checked ? [...evidence, card.id] : evidence.filter(id => id !== card.id))} /> {card.id} {card.title}</label>)}
        <button className="primary" disabled={busy || !!c.my_submission || c.questions.some(q => !answers[q.id])} onClick={() => run(() => campaignAction(game.id, seat, { action: "submit", answers, evidence }))}>{c.my_submission ? "陣営の回答は確定済み" : "陣営の代表として確定する"}</button>
      </div>}
      {seat === 1 && <button className="ghost" disabled={busy || !c.can_advance} onClick={() => run(() => advanceMystery(game.id, seat))}>次へ進む</button>}
      {!c.can_advance && <p>対象者のカード取得、または全陣営の回答を待っています。</p>}
    </>}
    {c.results && <div className="endingCard"><h3>陣営別の結果</h3><p>勝利：{c.results.winners.map(label).join("、")}{c.results.winners.length > 1 ? "（同点）" : ""}</p>{Object.entries(c.results.scores).map(([team, score]) => <p key={team}>{label(team)}：{score}点</p>)}{c.results.rounds.map((r, index) => <p key={index}>{label(r.team)} / {r.question}：回答 {r.submitted_label} ／ 正解 {r.answer_label} ／ {r.score}点</p>)}</div>}
    {error && <pre className="error">{error}</pre>}
  </div>;
}
