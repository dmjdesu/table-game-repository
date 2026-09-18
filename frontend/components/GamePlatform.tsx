"use client";

import { useState } from "react";
import MysteryBuilder from "./MysteryBuilder";
import VillageBuilder from "./VillageBuilder";

export default function GamePlatform() {
  const [mode, setMode] = useState<"werewolf" | "mystery">("werewolf");

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">AI GAME MASTER / LOCAL MVP</p>
          <h1>正体隠匿も、物語進行も、同じ基盤で。</h1>
          <p className="lead">
            ルールと秘密情報はDjangoが管理し、AIは許可された情報だけを使って会話・演出する。
            人狼とGMレスマダミスを同じゲームエンジンへ寄せる実験基盤。
          </p>
        </div>
        <div className="brandMark">GM</div>
      </header>

      <nav className="modeTabs" aria-label="ゲームモード">
        <button className={mode === "werewolf" ? "active" : ""} onClick={() => setMode("werewolf")}>
          AI人狼
        </button>
        <button className={mode === "mystery" ? "active" : ""} onClick={() => setMode("mystery")}>
          GMレス・マダミス
        </button>
      </nav>

      {mode === "werewolf" ? <VillageBuilder embedded /> : <MysteryBuilder />}
    </main>
  );
}
