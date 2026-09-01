import { useMemo } from "react";
import type { TileMap } from "../types";
import { expandRoadLevels, expandTiles } from "./WorldProps";

const WIDTH: Record<number, number> = { 1: 1.05, 2: 0.82, 3: 0.62, 4: 0.48 };
const COLOR: Record<number, string> = {
  1: "#1e1e24",
  2: "#282830",
  3: "#323238",
  4: "#3a3a42",
};
const ELEV: Record<number, number> = { 1: 0.06, 2: 0.05, 3: 0.04, 4: 0.035 };

export function Roads({ tiles }: { tiles: TileMap }) {
  const { segments, curbs } = useMemo(() => collectRoads(tiles), [tiles]);
  if (!segments.length) return null;

  return (
    <group>
      {segments.map((seg) => (
        <group key={seg.key} position={[seg.x + 0.5, ELEV[seg.level] ?? 0.04, seg.z + 0.5]}>
          <mesh rotation={[-Math.PI / 2, 0, seg.rot]} receiveShadow castShadow>
            <planeGeometry args={[seg.len, seg.w]} />
            <meshStandardMaterial color={seg.color} roughness={0.82} metalness={0.12} />
          </mesh>
          {seg.level <= 2 ? (
            <mesh rotation={[-Math.PI / 2, 0, seg.rot]} position={[0, 0.008, 0]}>
              <planeGeometry args={[seg.len * 0.92, 0.06]} />
              <meshStandardMaterial color="#e8d060" emissive="#443808" emissiveIntensity={0.08} />
            </mesh>
          ) : null}
        </group>
      ))}
      {curbs.map((c) => (
        <mesh key={c.key} position={[c.x + 0.5, 0.025, c.z + 0.5]} receiveShadow>
          <boxGeometry args={[c.w, 0.05, c.d]} />
          <meshStandardMaterial color="#6a6458" roughness={0.95} />
        </mesh>
      ))}
    </group>
  );
}

type Seg = {
  key: string;
  x: number;
  z: number;
  len: number;
  w: number;
  level: number;
  color: string;
  rot: number;
};

function collectRoads(tiles: TileMap) {
  const types = expandTiles(tiles);
  const levels = expandRoadLevels(tiles);
  const segments: Seg[] = [];
  const curbs: { key: string; x: number; z: number; w: number; d: number }[] = [];
  const seenH = new Set<string>();
  const seenV = new Set<string>();
  const w = tiles.width;
  const h = tiles.height;

  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      if (types[i] !== "road") continue;
      const level = levels[i] || 3;
      const roadW = WIDTH[level] ?? 0.5;
      const color = COLOR[level] ?? "#444";

      const hk = `h-${y}-${Math.floor(x / 3)}`;
      if (!seenH.has(hk) && x + 1 < w && types[y * w + x + 1] === "road") {
        seenH.add(hk);
        let len = 1;
        while (x + len < w && types[y * w + x + len] === "road") len++;
        segments.push({ key: `h${x}-${y}`, x: x + len / 2 - 0.5, z: y, len, w: roadW, level, color, rot: 0 });
        if (level <= 2 && len >= 2) {
          curbs.push({ key: `ch${x}-${y}`, x: x + len / 2 - 0.5, z: y - roadW / 2 - 0.04, w: len, d: 0.08 });
          curbs.push({ key: `ch2${x}-${y}`, x: x + len / 2 - 0.5, z: y + roadW / 2 + 0.04, w: len, d: 0.08 });
        }
      }

      const vk = `v-${x}-${Math.floor(y / 3)}`;
      if (!seenV.has(vk) && y + 1 < h && types[(y + 1) * w + x] === "road") {
        seenV.add(vk);
        let len = 1;
        while (y + len < h && types[(y + len) * w + x] === "road") len++;
        segments.push({ key: `v${x}-${y}`, x, z: y + len / 2 - 0.5, len, w: roadW, level, color, rot: Math.PI / 2 });
      }
    }
  }

  return { segments: segments.slice(0, 6000), curbs: curbs.slice(0, 4000) };
}
