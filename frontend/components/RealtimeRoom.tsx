"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { useGameSocket } from "../lib/useGameSocket";

type Props<TGame> = {
  gameId: string;
  seat: number;
  onGameSnapshot?: (game: TGame) => void;
};

function previewCost(content: string) {
  const length = content.replace(/\s/g, "").length;
  if (length <= 40) return 1;
  if (length <= 120) return 2;
  return 3;
}

function formatSeconds(value: number | null) {
  if (value === null) return "--:--";
  const safe = Math.max(0, value);
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export default function RealtimeRoom<TGame>({
  gameId,
  seat,
  onGameSnapshot,
}: Props<TGame>) {
  const { snapshot, status, error, sendChat, advancePhase } =
    useGameSocket<TGame>(gameId, seat, onGameSnapshot);
  const [draft, setDraft] = useState("");
  const [clock, setClock] = useState<number | null>(null);

  const timer = snapshot?.realtime.phase_timer;

  useEffect(() => {
    if (!timer?.ends_at) {
      setClock(null);
      return;
    }

    const update = () => {
      const remaining = Math.ceil(
        (new Date(timer.ends_at as string).getTime() - Date.now()) / 1000,
      );
      setClock(Math.max(0, remaining));
    };
    update();
    const id = window.setInterval(update, 1000);
    return () => window.clearInterval(id);
  }, [timer?.ends_at]);

  const cost = useMemo(() => previewCost(draft), [draft]);
  const apRemaining = snapshot?.realtime.speech_ap_remaining ?? 0;
  const apTotal = snapshot?.realtime.speech_ap_total ?? 0;
  const messages = snapshot?.realtime.messages ?? [];
  const game = snapshot?.game as unknown as Record<string, unknown> | undefined;
  const me = game?.me as
    | { role?: string; known_allies?: Array<{ seat: number; display_name: string }> }
    | undefined;

  function submit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content) return;
    if (sendChat(content)) setDraft("");
  }

  return (
    <div className="realtimeRoom">
      <div className="realtimeHeader">
        <div>
          <span className={`socketDot ${status}`} />
          <b>{status === "connected" ? "LIVE" : status.toUpperCase()}</b>
          <small>{timer?.phase_key ?? "phase loading"}</small>
        </div>
        <div className="realtimeMetrics">
          <span><small>TIME</small><b>{formatSeconds(clock)}</b></span>
          <span><small>AP</small><b>{apRemaining}/{apTotal}</b></span>
        </div>
      </div>

      {me?.role && (
        <div className="roleNotice">
          <span>YOUR ROLE</span>
          <b>{me.role}</b>
          {me.known_allies?.length ? (
            <small>
              仲間: {me.known_allies.map((ally) => `${ally.display_name}(Seat ${ally.seat})`).join(" / ")}
            </small>
          ) : null}
        </div>
      )}

      <div className="chatTimeline">
        {messages.length === 0 ? (
          <p className="chatEmpty">まだ発言はない。静かな村ほどだいたい後で揉める。</p>
        ) : (
          messages.map((message) => (
            <article key={message.id} className={message.seat === seat ? "mine" : ""}>
              <div>
                <b>{message.display_name}</b>
                <small>Seat {message.seat} / -{message.ap_cost}AP</small>
              </div>
              <p>{message.content}</p>
            </article>
          ))
        )}
      </div>

      <form className="chatComposer" onSubmit={submit}>
        <input
          value={draft}
          maxLength={400}
          placeholder="発言する…"
          onChange={(event) => setDraft(event.target.value)}
        />
        <span className={cost > apRemaining ? "cost dangerText" : "cost"}>
          {cost} AP
        </span>
        <button
          className="primary"
          type="submit"
          disabled={status !== "connected" || !draft.trim() || cost > apRemaining}
        >
          送信
        </button>
      </form>

      <div className="realtimeFooter">
        <span>短文 1AP / 中文 2AP / 長文 3AP</span>
        {seat === 1 && (
          <button className="ghost compactButton" onClick={advancePhase}>
            Seat 1: 次フェーズ
          </button>
        )}
      </div>

      {error && <div className="socketError">{error}</div>}
    </div>
  );
}
