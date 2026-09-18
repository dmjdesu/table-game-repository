import type {
  CreatedGame,
  ImportedScenario,
  MysteryGame,
  Preset,
  ScenarioFormat,
  StrategyPreview,
  VillageConfig,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(body));
  }
  return body;
}

export async function getPresets(): Promise<{ presets: Preset[]; roles: Record<string, string> }> {
  return request("/presets/");
}

export async function previewStrategy(config: VillageConfig): Promise<StrategyPreview> {
  return request("/strategy/preview/", { method: "POST", body: JSON.stringify(config) });
}

export async function createGame(name: string, config: VillageConfig): Promise<CreatedGame> {
  return request("/games/", { method: "POST", body: JSON.stringify({ name, ...config }) });
}

export async function importScenario(rawText: string, sourceFormat: ScenarioFormat): Promise<ImportedScenario> {
  return request("/scenarios/import/", {
    method: "POST",
    body: JSON.stringify({ raw_text: rawText, source_format: sourceFormat }),
  });
}

export async function createMysteryGame(
  scenarioId: string,
  aiCount: number,
  aiCountVisibility: "exact" | "range" | "hidden",
): Promise<MysteryGame> {
  return request("/mystery/games/", {
    method: "POST",
    body: JSON.stringify({
      scenario_id: scenarioId,
      ai_count: aiCount,
      ai_count_visibility: aiCountVisibility,
    }),
  });
}

export async function getMysteryGame(gameId: string, seat?: number): Promise<MysteryGame> {
  return request(`/mystery/games/${gameId}/${seat ? `?seat=${seat}` : ""}`);
}

export async function advanceMystery(gameId: string, seat?: number): Promise<MysteryGame> {
  return request(`/mystery/games/${gameId}/advance/`, {
    method: "POST",
    body: JSON.stringify({ seat }),
  });
}

export async function performMysteryAction(
  gameId: string,
  seat: number,
  action: string,
  target = "",
): Promise<{ result: unknown; game: MysteryGame }> {
  return request(`/mystery/games/${gameId}/actions/`, {
    method: "POST",
    body: JSON.stringify({ seat, action, target }),
  });
}

export async function voteMystery(
  gameId: string,
  seat: number,
  targetCharacterId: string,
): Promise<MysteryGame> {
  return request(`/mystery/games/${gameId}/vote/`, {
    method: "POST",
    body: JSON.stringify({ seat, target_character_id: targetCharacterId }),
  });
}

export async function askMysteryGM(
  gameId: string,
  seat: number,
  question: string,
): Promise<{ text: string; source: string }> {
  return request(`/mystery/games/${gameId}/gm/help/`, {
    method: "POST",
    body: JSON.stringify({ seat, question }),
  });
}
