import { create } from "zustand";
import type { AgentView, BuildingView, Dashboard, PresidentView, Snapshot, TileMap } from "../types";

export type FollowTarget = "president" | number | null;
export type Selection =
  | { kind: "agent"; id: number }
  | { kind: "building"; id: number }
  | { kind: "president" }
  | null;

interface WorldStore {
  connected: boolean;
  tiles: TileMap | null;
  buildings: BuildingView[];
  agents: AgentView[];
  president: PresidentView | null;
  dashboard: Dashboard | null;
  cameraX: number;
  cameraZ: number;
  selection: Selection;
  follow: FollowTarget;
  apply: (msg: Snapshot) => void;
  setConnected: (value: boolean) => void;
  setCamera: (x: number, z: number) => void;
  select: (selection: Selection) => void;
  setFollow: (target: FollowTarget) => void;
}

export const useWorld = create<WorldStore>((set) => ({
  connected: false,
  tiles: null,
  buildings: [],
  agents: [],
  president: null,
  dashboard: null,
  cameraX: 0,
  cameraZ: 0,
  selection: null,
  follow: null,
  apply: (msg) =>
    set((state) => ({
      tiles: msg.tiles ?? state.tiles,
      buildings: msg.buildings ?? state.buildings,
      agents: msg.agents,
      president: msg.president,
      dashboard: msg.dashboard,
    })),
  setConnected: (connected) => set({ connected }),
  setCamera: (cameraX, cameraZ) => set({ cameraX, cameraZ }),
  select: (selection) => set({ selection }),
  setFollow: (follow) => set({ follow }),
}));
