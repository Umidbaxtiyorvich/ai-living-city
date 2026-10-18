export type TileRun = [string, string, number] | [string, string, number, number];

export interface TileMap {
  width: number;
  height: number;
  runs: TileRun[];
}

export interface BuildingView {
  id: number;
  type: string;
  category: string;
  x: number;
  y: number;
  width: number;
  height: number;
  levels: number;
  status: string;
  progress: number;
  residents: number;
  capacity: number;
  staff: number;
  job_slots: number;
  condition?: number;
  renovations?: number;
}

export interface AgentView {
  id: number;
  name: string;
  gender: string;
  age: number;
  stage: string;
  activity: string;
  x: number;
  y: number;
  profession: string | null;
  happiness: number;
  detail: string;
  avatar_seed: string;
  appearance: Record<string, unknown>;
  player_order?: string | null;
  player_order_note?: string;
  desk?: string | null;
  /** Latest inner monologue line from the citizen's mind. */
  thought?: string;
  awareness?: number;
}

export interface MindGoal {
  kind: string;
  text: string;
  progress: number;
}

export interface MindDetail {
  awareness: number;
  wisdom: number;
  thought: string;
  preferences: Record<string, number>;
  goals: MindGoal[];
  achieved: MindGoal[];
  achievements: number;
  study_hours: number;
  wishes: Record<string, number>;
}

export interface SocietyView {
  voice: { wish: string; text: string; strength: number }[];
  awareness: number;
  wisdom: number;
  achievements: number;
  studying_share: number;
  goals_active: number;
  thoughts: { id: number; name: string; thought: string }[];
  renewals: number;
}

export interface PresidentMind {
  intelligence: number;
  leadership: number;
  lessons_learned: number;
  responsiveness: number;
  thought: string;
  policy_weights: Record<string, number>;
}

export interface PresidentView {
  id: number;
  name: string;
  gender: string;
  age: number;
  activity: string;
  x: number;
  y: number;
  approval_rating: number;
  health: number;
  energy: number;
  emergency: string | null;
  avatar_seed: string;
  thought?: string;
}

export interface CityEvent {
  id: number;
  tick: number;
  day: number;
  type: string;
  severity: string;
  text: string;
  agent_ids: number[];
  building_ids: number[];
}

export interface LedgerItem {
  id: number;
  kind: string;
  desk: string;
  desk_label: string;
  title: string;
  text: string;
  status: string;
  agent_id: number | null;
  agent_name: string;
  created_day: number;
  created_specialist: boolean;
  result: string;
  input_file: string;
  output_file: string;
  progress: number;
  law_code: string;
  notes: { tick: number; day: number; text: string }[];
}

export interface Dashboard {
  time: {
    tick: number;
    day: number;
    label: string;
    hour: number;
    speed: number;
    is_night: boolean;
  };
  city_level: number;
  city_level_name: string;
  map_version: number;
  events: CityEvent[];
  stats: {
    population: number;
    adults: number;
    children: number;
    seniors: number;
    employed: number;
    unemployed: number;
    unemployment_rate: number;
    homeless: number;
    housing_shortage: number;
    happiness: number;
    budget: number;
    gdp: number;
    buildings_open: number;
    buildings_under_construction: number;
    coverage: Record<string, number>;
  };
  economy: {
    budget: number;
    gdp: number;
    taxes: { income_tax: number; business_tax: number; property_tax: number };
    monthly_net: number;
    in_deficit: boolean;
  };
  weather: { condition: string; temperature: number; wind: number };
  president: PresidentView | null;
  current_decision: {
    id: number;
    status: string;
    rationale: string;
    cost: number;
    concern: { code: string; description: string; action: string; priority_name: string };
  } | null;
  emergency: { type: string; text: string } | null;
  society?: SocietyView;
  president_mind?: PresidentMind | null;
  player?: {
    owner_name: string;
    role: "president" | "prime_minister";
    standing: { id: number; text: string; done: boolean; result: string }[];
    log: { tick: number; role: string; text: string; reply: string }[];
    tasks?: LedgerItem[];
    decrees?: LedgerItem[];
    laws?: LedgerItem[];
    desks?: { desk: string; agent_id: number; agent_name: string; profession: string | null }[];
    coding?: {
      coder_id: number;
      coder_name: string;
      desk: string;
      task_id: number;
      filename: string;
      visible: string;
      typed: number;
      total: number;
      progress: number;
      done: boolean;
      path: string;
    } | null;
  };
  performance: { last_tick_ms: number; ticks_processed: number; agents: number };
  urban?: {
    traffic_congestion?: number;
    parking?: { capacity: number; demand: number; shortage: number; utilization?: number };
    transport?: { routes: number; stops: number };
    utilities?: { blackout: boolean; power_coverage: number; water_coverage?: number };
    street_lights?: number;
    landmarks?: { kind: string; label: string; x?: number; y?: number }[];
  };
}

export interface Snapshot {
  kind: "snapshot" | "tick";
  tiles?: TileMap;
  buildings?: BuildingView[];
  agents: AgentView[];
  president: PresidentView | null;
  dashboard: Dashboard;
}
