"use client";

import { useEffect, useMemo, useState } from "react";
import { createGame, getPresets, previewStrategy } from "../lib/api";
import RealtimeRoom from "./RealtimeRoom";
import type { CreatedGame, Preset, RoleKey, StrategyPreview, VillageConfig } from "../lib/types";

const roleLabels: Record<RoleKey, string> = {
  villager: "村人",
  wolf: "人狼",
  seer: "占い師",
  medium: "霊媒師",
  guard: "狩人",
  madman: "狂人",
};

const emptyConfig: VillageConfig = {
  player_count: 8,
  roles: { villager: 3, wolf: 2, seer: 1, medium: 1, guard: 1, madman: 0 },
  first_day_divination: true,
  consecutive_guard: false,
  role_missing: false,
  revote: true,
  speech_limit: 8,
  ai_count: 4,
  ai_difficulty: "standard",
  ai_count_visibility: "range",
};

export default function VillageBuilder({ embedded = false }: { embedded?: boolean }) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [config, setConfig] = useState<VillageConfig>(emptyConfig);
  const [name, setName] = useState("夜明け前の村");
  const [preview, setPreview] = useState<StrategyPreview | null>(null);
  const [game, setGame] = useState<CreatedGame | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [seat, setSeat] = useState(1);

  useEffect(() => {
    getPresets().then((data) => setPresets(data.presets)).catch(() => setError("Django APIに接続できません。"));
  }, []);

  const roleTotal = useMemo(() => Object.values(config.roles).reduce((a, b) => a + b, 0), [config.roles]);

  function applyPreset(preset: Preset) {
    setConfig({
      player_count: preset.player_count,
      roles: { villager: 0, wolf: 0, seer: 0, medium: 0, guard: 0, madman: 0, ...preset.roles },
      first_day_divination: preset.first_day_divination,
      consecutive_guard: preset.consecutive_guard,
      role_missing: preset.role_missing,
      revote: preset.revote,
      speech_limit: preset.speech_limit,
      ai_count: preset.ai_count,
      ai_difficulty: preset.ai_difficulty,
      ai_count_visibility: preset.ai_count_visibility,
    });
    setGame(null);
    setPreview(null);
    setError("");
  }

  function changeRole(role: RoleKey, delta: number) {
    setConfig((current) => ({
      ...current,
      roles: { ...current.roles, [role]: Math.max(0, current.roles[role] + delta) },
    }));
  }

  async function handlePreview() {
    setLoading(true);
    setError("");
    try {
      setPreview(await previewStrategy(config));
    } catch (e) {
      setError(`設定を確認してね: ${e instanceof Error ? e.message : "unknown error"}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate() {
    setLoading(true);
    setError("");
    try {
      const created = await createGame(name, config);
      setGame(created);
      setPreview(created);
      setSeat(1);
    } catch (e) {
      setError(`村を作れなかった: ${e instanceof Error ? e.message : "unknown error"}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={embedded ? "embeddedApp" : ""}>
      <section className="panel">
        <div className="sectionHead"><div><span>01</span><h2>公式プリセット</h2></div><p>迷ったらここ。設定画面で人類を消耗させない。</p></div>
        <div className="presetGrid">
          {presets.map((preset) => (
            <button key={preset.id} className="presetCard" onClick={() => applyPreset(preset)}>
              <strong>{preset.label}</strong>
              <span>{preset.description}</span>
              <small>{preset.player_count}人 / AI {preset.ai_count}人</small>
            </button>
          ))}
        </div>
      </section>

      <section className="panel twoCol">
        <div>
          <div className="sectionHead"><div><span>02</span><h2>村の構成</h2></div></div>
          <label className="field">村名<input value={name} onChange={(e) => setName(e.target.value)} /></label>
          <div className="inlineFields">
            <label className="field">参加人数<input type="number" min={5} max={15} value={config.player_count} onChange={(e) => setConfig({ ...config, player_count: Number(e.target.value) })} /></label>
            <label className="field">AI人数<input type="number" min={0} max={config.player_count} value={config.ai_count} onChange={(e) => setConfig({ ...config, ai_count: Number(e.target.value) })} /></label>
            <label className="field">発言回数<input type="number" min={3} max={20} value={config.speech_limit} onChange={(e) => setConfig({ ...config, speech_limit: Number(e.target.value) })} /></label>
          </div>

          <div className="roles">
            {(Object.keys(roleLabels) as RoleKey[]).map((role) => (
              <div className="roleRow" key={role}>
                <span>{roleLabels[role]}</span>
                <div><button onClick={() => changeRole(role, -1)}>-</button><b>{config.roles[role]}</b><button onClick={() => changeRole(role, 1)}>+</button></div>
              </div>
            ))}
          </div>
          <p className={roleTotal === config.player_count ? "total ok" : "total bad"}>役職合計 {roleTotal} / {config.player_count}</p>
        </div>

        <div>
          <div className="sectionHead"><div><span>03</span><h2>AI・詳細ルール</h2></div></div>
          <label className="field">AI難易度<select value={config.ai_difficulty} onChange={(e) => setConfig({ ...config, ai_difficulty: e.target.value as VillageConfig["ai_difficulty"] })}><option value="casual">Casual</option><option value="standard">Standard</option><option value="expert">Expert</option></select></label>
          <label className="field">AI人数の公開<select value={config.ai_count_visibility} onChange={(e) => setConfig({ ...config, ai_count_visibility: e.target.value as VillageConfig["ai_count_visibility"] })}><option value="exact">正確に公開</option><option value="range">範囲だけ公開</option><option value="hidden">完全非公開</option></select></label>
          <div className="checks">
            {[
              ["first_day_divination", "初日占いあり"],
              ["consecutive_guard", "連続ガードあり"],
              ["role_missing", "役欠けあり"],
              ["revote", "同票時に再投票"],
            ].map(([key, label]) => (
              <label key={key}><input type="checkbox" checked={Boolean(config[key as keyof VillageConfig])} onChange={(e) => setConfig({ ...config, [key]: e.target.checked })} />{label}</label>
            ))}
          </div>
          <div className="actions"><button className="ghost" disabled={loading} onClick={handlePreview}>戦略をプレビュー</button><button className="primary" disabled={loading} onClick={handleCreate}>村を作成</button></div>
          {error && <pre className="error">{error}</pre>}
        </div>
      </section>

      {preview && (
        <section className="panel result">
          <div className="sectionHead"><div><span>04</span><h2>抽象状態・戦略キャッシュ</h2></div></div>
          {game && <div className="created"><strong>村を作成した</strong><span>ID: {game.id}</span><span>{game.ai_presence_hint}</span></div>}
          <code className="cacheKey">{preview.strategy_profile.cache_key}</code>
          <div className="tags">{Object.entries(preview.abstract_state).map(([key, value]) => <span key={key}>{key}: {String(value)}</span>)}</div>
          <div className="strategyGrid"><div><h3>村陣営</h3>{preview.strategy_profile.village_priorities.map((x) => <p key={x}>{x}</p>)}</div><div><h3>人狼陣営</h3>{preview.strategy_profile.wolf_priorities.map((x) => <p key={x}>{x}</p>)}</div></div>
        </section>
      )}

      {game && (
        <section className="panel">
          <div className="sectionHead">
            <div><span>05</span><h2>リアルタイム村</h2></div>
            <p>WebSocket / 共通フェーズ時計 / 発言AP</p>
          </div>
          <label className="field">
            操作する座席
            <select value={seat} onChange={(event) => setSeat(Number(event.target.value))}>
              {game.players.map((player) => (
                <option key={player.seat} value={player.seat}>
                  Seat {player.seat} / {player.display_name}
                </option>
              ))}
            </select>
          </label>
          <RealtimeRoom<CreatedGame> gameId={game.id} seat={seat} />
        </section>
      )}
    </div>
  );
}
