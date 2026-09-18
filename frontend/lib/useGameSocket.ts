"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type RealtimeMessage = {
  id: number;
  seat: number;
  display_name: string;
  content: string;
  ap_cost: number;
  phase_key: string;
  created_at: string;
};

export type PhaseTimer = {
  phase_key: string;
  started_at: string | null;
  ends_at: string | null;
  remaining_seconds: number | null;
  server_now: string;
};

export type RealtimeState = {
  phase_timer: PhaseTimer;
  speech_ap_total: number;
  speech_ap_remaining: number;
  messages: RealtimeMessage[];
};

export type RealtimeEnvelope<TGame> = {
  type: "snapshot";
  reason: string;
  game: TGame;
  realtime: RealtimeState;
};

type SocketStatus = "connecting" | "connected" | "disconnected";

const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE_URL ??
  (typeof window !== "undefined" && window.location.protocol === "https:"
    ? "wss://localhost:8000/ws"
    : "ws://localhost:8000/ws");

export function useGameSocket<TGame>(
  gameId: string | null,
  seat: number,
  onGameSnapshot?: (game: TGame) => void,
) {
  const [snapshot, setSnapshot] = useState<RealtimeEnvelope<TGame> | null>(null);
  const [status, setStatus] = useState<SocketStatus>("disconnected");
  const [error, setError] = useState("");
  const socketRef = useRef<WebSocket | null>(null);
  const callbackRef = useRef(onGameSnapshot);

  useEffect(() => {
    callbackRef.current = onGameSnapshot;
  }, [onGameSnapshot]);

  useEffect(() => {
    if (!gameId || seat < 1) {
      setStatus("disconnected");
      return;
    }

    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (disposed) return;
      setStatus("connecting");
      const socket = new WebSocket(`${WS_BASE}/games/${gameId}/?seat=${seat}`);
      socketRef.current = socket;

      socket.onopen = () => {
        if (disposed) return;
        setStatus("connected");
        setError("");
      };

      socket.onmessage = (event) => {
        if (disposed) return;
        try {
          const data = JSON.parse(event.data);

          if (data.type === "snapshot") {
            const next = data as RealtimeEnvelope<TGame>;
            setSnapshot(next);
            callbackRef.current?.(next.game);
            return;
          }

          if (data.type === "chat.message") {
            setSnapshot((current) => {
              if (!current) return current;
              const exists = current.realtime.messages.some(
                (message) => message.id === data.message.id,
              );
              if (exists) return current;
              return {
                ...current,
                realtime: {
                  ...current.realtime,
                  messages: [...current.realtime.messages, data.message],
                },
              };
            });
            return;
          }

          if (data.type === "error") {
            setError(data.message ?? "WebSocketでエラーが発生しました。");
          }
        } catch {
          setError("WebSocketメッセージを解釈できませんでした。");
        }
      };

      socket.onerror = () => {
        if (!disposed) setError("リアルタイム接続でエラーが発生しました。");
      };

      socket.onclose = () => {
        if (disposed) return;
        setStatus("disconnected");
        reconnectTimer = setTimeout(connect, 1500);
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket && socket.readyState <= WebSocket.OPEN) socket.close();
    };
  }, [gameId, seat]);

  const send = useCallback((payload: Record<string, unknown>) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setError("リアルタイム接続がまだ利用できません。");
      return false;
    }
    socket.send(JSON.stringify(payload));
    return true;
  }, []);

  const sendChat = useCallback(
    (content: string) => send({ type: "chat.send", content }),
    [send],
  );

  const advancePhase = useCallback(
    () => send({ type: "phase.advance" }),
    [send],
  );

  const refresh = useCallback(
    () => send({ type: "state.refresh" }),
    [send],
  );

  return {
    snapshot,
    status,
    error,
    sendChat,
    advancePhase,
    refresh,
  };
}
