import { useEffect, useState } from "react";

/**
 * Rigged human models, described by `public/models/humans/manifest.json`.
 *
 * The renderer does not hard-code any asset: drop any skinned glTF/GLB with
 * idle/walk clips into `public/models/humans/`, list it in the manifest, and the
 * citizens near the camera wear it. With no manifest the city falls back to the
 * procedural figures, so the app always runs.
 *
 * `scripts/fetch-humans.mjs` writes a starter manifest. For a more realistic
 * cast, the Quaternius "Universal Base Characters" + "Universal Animation
 * Library" packs (CC0) drop straight in — see the README.
 */
export type ClipRole = "idle" | "walk" | "run" | "sit" | "work";

export interface HumanModelEntry {
  id: string;
  /** Path relative to `public/`, e.g. "models/humans/Soldier.glb". */
  url: string;
  gender?: "male" | "female" | "any";
  /** Clip names per role. Missing roles are matched by name heuristics. */
  clips?: Partial<Record<ClipRole, string>>;
  /**
   * Another GLB whose animations drive this model — for characters shipped
   * without locomotion clips but sharing the same skeleton (e.g. Mixamo rigs).
   */
  clipSource?: string;
  /** Material-name substrings recoloured with the citizen's clothing colour. */
  tint?: string[];
  /** Material-name substrings recoloured with the citizen's skin tone. */
  skin?: string[];
  /** Extra yaw in radians if the model does not face +Z. */
  yaw?: number;
}

const BASE = import.meta.env.BASE_URL ?? "/";

export function assetUrl(path: string): string {
  if (/^https?:/.test(path)) return path;
  return `${BASE.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

let manifest: Promise<HumanModelEntry[]> | null = null;

function loadManifest(): Promise<HumanModelEntry[]> {
  if (!manifest) {
    manifest = fetch(assetUrl("models/humans/manifest.json"))
      .then((response) => (response.ok ? response.json() : []))
      .then((data: unknown) => (Array.isArray(data) ? (data as HumanModelEntry[]) : []))
      .catch(() => []);
  }
  return manifest;
}

/** The model list; `null` while loading, empty when no models are installed. */
export function useHumanManifest(): HumanModelEntry[] | null {
  const [entries, setEntries] = useState<HumanModelEntry[] | null>(null);
  useEffect(() => {
    let alive = true;
    void loadManifest().then((list) => {
      if (alive) setEntries(list);
    });
    return () => {
      alive = false;
    };
  }, []);
  return entries;
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Deterministic model choice: the same citizen always wears the same body. */
export function pickModel(
  entries: HumanModelEntry[],
  seed: string,
  gender: string,
): HumanModelEntry | null {
  if (entries.length === 0) return null;
  const matching = entries.filter((entry) => !entry.gender || entry.gender === "any" || entry.gender === gender);
  const pool = matching.length > 0 ? matching : entries;
  return pool[hash(seed) % pool.length];
}

const CLIP_PATTERNS: Record<ClipRole, RegExp> = {
  idle: /idle|stand|breath/i,
  walk: /walk/i,
  run: /run|jog/i,
  sit: /sit/i,
  work: /work|type|interact|pick/i,
};

/** Finds the clip name for a role among the names a model provides. */
export function clipFor(role: ClipRole, names: string[], entry: HumanModelEntry): string | null {
  const wanted = entry.clips?.[role];
  if (wanted && names.includes(wanted)) return wanted;
  const pattern = CLIP_PATTERNS[role];
  // Prefer plain loops ("Walk") over variants ("Walk_Left", "Walk_Formal").
  const found = names.filter((name) => pattern.test(name)).sort((a, b) => a.length - b.length);
  return found[0] ?? null;
}
