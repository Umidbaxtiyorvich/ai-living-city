import { create } from "zustand";

/** [id, x, y, task, stage, gender initial, carrying, is player] — streamed ten times a second. */
export type PersonRow = [number, number, number, string, string, string, string, number];
/** [id, kind, x, y, moving, young] */
export type AnimalRow = [number, string, number, number, number, number];

export interface Blueprint {
  kind: string;
  name: string;
  wood: number;
  stone: number;
  w: number;
  h: number;
  category: string;
  known: boolean;
}

export interface Looks {
  id: number;
  name: string;
  skin: string;
  hair: string;
  clothes: string;
  height: number;
}

export interface Petition {
  id: number;
  person_id: number;
  name: string;
  settlement: string;
  kind: string;
  text: string;
  day: number;
  status: string;
  arrived: boolean;
  answer: string;
  reply: string;
}

export interface CustomRule {
  key: string;
  text: string;
  day: number;
}

export interface CivBuilding {
  id: number;
  kind: string;
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
  levels: number;
  category: string;
  progress: number;
  complete: boolean;
  wall: string;
  roof: string;
  style: number;
  growth: number;
  crop?: string;
  residents: number;
  settlement: number;
}

export interface CivSettlement {
  id: number;
  name: string;
  x: number;
  y: number;
  founded_day: number;
  population: number;
  rank: string;
  storage: { food: number; wood: number; stone: number; meat?: number };
  leader_id: number | null;
}

export interface ChronicleItem {
  day: number;
  year: number;
  text: string;
  kind: string;
}

export interface CivStats {
  population: number;
  births: number;
  deaths: number;
  homes: number;
  buildings: number;
  sites: number;
  families: number;
  homeless: number;
  awareness: number;
  happiness: number;
  era: string;
  known: { key: string; name: string }[];
  researching: { name: string; progress: number } | null;
  tick_ms: number;
}

export interface CivTime {
  tick: number;
  day: number;
  year: number;
  day_of_year: number;
  hour: number;
  night: boolean;
  season?: string;
}

export interface Resources {
  trees: number[];
  tree_size: number[];
  bushes: number[];
}

export interface CivFrame {
  kind: "snapshot" | "frame";
  time: CivTime;
  speed: number;
  people: PersonRow[];
  stats: CivStats;
  settlements: CivSettlement[];
  world?: { width: number; height: number; terrain: string };
  terrain_changes?: [number, string][];
  resources?: Resources;
  buildings?: CivBuilding[];
  looks?: Looks[];
  chronicle?: ChronicleItem[];
  labels?: Record<string, string>;
  animals?: AnimalRow[];
  player_id?: number | null;
  player_auto?: boolean;
  blueprints?: Blueprint[];
  petitions?: Petition[];
  customs?: CustomRule[];
}

interface CivStore {
  connected: boolean;
  width: number;
  height: number;
  terrain: string;
  terrainVersion: number;
  resources: Resources;
  buildings: CivBuilding[];
  people: PersonRow[];
  looks: Map<number, Looks>;
  settlements: CivSettlement[];
  chronicle: ChronicleItem[];
  labels: Record<string, string>;
  animals: AnimalRow[];
  playerId: number | null;
  playerAuto: boolean;
  blueprints: Blueprint[];
  petitions: Petition[];
  customs: CustomRule[];
  /** Blueprint being placed with the next click on the ground. */
  placing: string | null;
  creative: boolean;
  message: string;
  stats: CivStats | null;
  time: CivTime | null;
  speed: number;
  selected: number | null;
  follow: number | null;
  /** A camera move requested by the HUD (fly to a settlement). */
  focus: { x: number; z: number; n: number } | null;
  apply: (frame: CivFrame) => void;
  setConnected: (value: boolean) => void;
  select: (id: number | null) => void;
  setFollow: (id: number | null) => void;
  flyTo: (x: number, z: number) => void;
  setPlacing: (kind: string | null) => void;
  setCreative: (value: boolean) => void;
  say: (message: string) => void;
}

export const useCiv = create<CivStore>((set, get) => ({
  connected: false,
  width: 0,
  height: 0,
  terrain: "",
  terrainVersion: 0,
  resources: { trees: [], tree_size: [], bushes: [] },
  buildings: [],
  people: [],
  looks: new Map(),
  settlements: [],
  chronicle: [],
  labels: {},
  animals: [],
  playerId: null,
  playerAuto: false,
  blueprints: [],
  petitions: [],
  customs: [],
  placing: null,
  creative: false,
  message: "",
  stats: null,
  time: null,
  speed: 1,
  selected: null,
  follow: null,
  focus: null,
  apply: (frame) => {
    const state = get();
    const patch: Partial<CivStore> = {
      people: frame.people,
      stats: frame.stats,
      time: frame.time,
      speed: frame.speed,
      settlements: frame.settlements,
    };
    if (frame.kind === "snapshot") {
      patch.looks = new Map();
    }
    if (frame.world) {
      patch.width = frame.world.width;
      patch.height = frame.world.height;
      patch.terrain = frame.world.terrain;
      patch.terrainVersion = state.terrainVersion + 1;
    }
    if (frame.terrain_changes && frame.terrain_changes.length) {
      const chars = (patch.terrain ?? state.terrain).split("");
      for (const [index, code] of frame.terrain_changes) chars[index] = code;
      patch.terrain = chars.join("");
      patch.terrainVersion = (patch.terrainVersion ?? state.terrainVersion) + 1;
    }
    if (frame.resources) patch.resources = frame.resources;
    if (frame.buildings) patch.buildings = frame.buildings;
    if (frame.chronicle) patch.chronicle = frame.chronicle;
    if (frame.labels) patch.labels = frame.labels;
    if (frame.animals) patch.animals = frame.animals;
    if (frame.player_id !== undefined) {
      patch.playerId = frame.player_id ?? null;
      // Start the camera on the player's own character.
      if (state.playerId == null && frame.player_id != null && state.follow == null) {
        patch.follow = frame.player_id;
      }
    }
    if (frame.blueprints) patch.blueprints = frame.blueprints;
    if (frame.player_auto !== undefined) patch.playerAuto = frame.player_auto;
    if (frame.petitions) patch.petitions = frame.petitions;
    if (frame.customs) patch.customs = frame.customs;
    if (frame.looks && frame.looks.length) {
      const looks = new Map(patch.looks ?? state.looks);
      for (const item of frame.looks) looks.set(item.id, item);
      patch.looks = looks;
    }
    set(patch);
  },
  setConnected: (connected) => set({ connected }),
  select: (selected) => set({ selected }),
  setFollow: (follow) => set({ follow }),
  flyTo: (x, z) => set((s) => ({ focus: { x, z, n: (s.focus?.n ?? 0) + 1 }, follow: null })),
  setPlacing: (placing) => set({ placing }),
  setCreative: (creative) => set({ creative }),
  say: (message) => set({ message }),
}));

/** Sends one command for the player's character and shows the reply. */
export async function act(body: Record<string, unknown>): Promise<{ reply?: string; ok?: boolean }> {
  try {
    const result = await civPost<{ reply?: string; ok?: boolean; detail?: string }>("/api/civ/player", body);
    const text = result.reply ?? result.detail ?? "";
    if (text) useCiv.getState().say(text);
    return result;
  } catch {
    useCiv.getState().say("Server bilan aloqa yo'q");
    return { ok: false };
  }
}

let socket: WebSocket | null = null;
let retry = 0;
let wanted = 0;

export function connectCiv(): () => void {
  wanted += 1;
  const open = () => {
    if (socket && socket.readyState <= WebSocket.OPEN) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/civ`);
    socket = ws;
    ws.onopen = () => {
      retry = 0;
      useCiv.getState().setConnected(true);
    };
    ws.onmessage = (event) => useCiv.getState().apply(JSON.parse(event.data) as CivFrame);
    ws.onclose = () => {
      useCiv.getState().setConnected(false);
      if (socket === ws) socket = null;
      if (wanted <= 0) return;
      retry += 1;
      window.setTimeout(open, Math.min(8000, 500 * 2 ** retry));
    };
  };
  open();
  return () => {
    wanted -= 1;
    if (wanted <= 0) {
      socket?.close();
      socket = null;
    }
  };
}

export async function civPost<T = unknown>(path: string, body: unknown = {}): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return (await res.json()) as T;
}
