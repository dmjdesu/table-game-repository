export type RoleKey = "villager" | "wolf" | "seer" | "medium" | "guard" | "madman";

export type VillageConfig = {
  player_count: number;
  roles: Record<RoleKey, number>;
  first_day_divination: boolean;
  consecutive_guard: boolean;
  role_missing: boolean;
  revote: boolean;
  speech_limit: number;
  ai_count: number;
  ai_difficulty: "casual" | "standard" | "expert";
  ai_count_visibility: "exact" | "range" | "hidden";
};

export type Preset = Omit<VillageConfig, "roles"> & {
  id: string;
  label: string;
  description: string;
  roles: Partial<Record<RoleKey, number>>;
};

export type StrategyPreview = {
  abstract_state: Record<string, string | number>;
  strategy_profile: {
    cache_key: string;
    village_priorities: string[];
    wolf_priorities: string[];
    decision_layers: string[];
  };
};

export type CreatedGame = StrategyPreview & {
  id: string;
  name: string;
  game_type: string;
  status: string;
  player_count: number;
  ai_presence_hint: string;
  players: { seat: number; display_name: string }[];
};

export type ScenarioFormat = "yaml" | "json" | "markdown";

export type ScenarioIssue = {
  level: "error" | "warning";
  code: string;
  message: string;
  path: string;
};

export type ScenarioValidationReport = {
  valid: boolean;
  errors: ScenarioIssue[];
  warnings: ScenarioIssue[];
  summary: Record<string, number>;
};

export type ScenarioDefinition = {
  title: string;
  players: number;
  characters: Array<{
    id: string;
    name: string;
    role: string;
    public_profile: string;
    secrets: string[];
    objectives: string[];
  }>;
  truth: Record<string, unknown>;
  evidence: Array<{ id: string; title: string; content: string; visibility: string }>;
  phases: Array<{
    id: string;
    label: string;
    type: string;
    duration_seconds: number;
    start_evidence: string[];
    instructions: string;
  }>;
  events: unknown[];
  endings: unknown[];
};

export type ImportedScenario = {
  id: string;
  title: string;
  game_type: string;
  source_format: string;
  status: "draft" | "ready" | "invalid";
  validation_report: ScenarioValidationReport;
  definition?: ScenarioDefinition;
};

export type MysteryPlayer = {
  seat: number;
  display_name: string;
  character_id: string;
  character_name: string;
  role: string;
  public_profile: string;
};

export type MysteryGame = {
  id: string;
  name: string;
  game_type: "murder_mystery";
  status: string;
  ai_presence_hint: string;
  players: MysteryPlayer[];
  me: (MysteryPlayer & { secrets: string[]; objectives: string[] }) | null;
  phase: {
    id: string;
    label: string;
    type: string;
    duration_seconds: number;
    start_evidence: string[];
    instructions: string;
  } | null;
  evidence: Array<{ id: string; title: string; content: string }>;
  votes_cast: number;
  finished: boolean;
  resolution: {
    ending_id: string | null;
    label: string;
    text: string;
    truth: Record<string, unknown>;
  } | null;
};
