import { useMemo } from "react";
import type { TileMap } from "../types";

export function expandTiles(tiles: TileMap): string[] {
  const out = new Array<string>(tiles.width * tiles.height);
  let i = 0;
  for (const run of tiles.runs) {
    const length = run[run.length - 1] as number;
    const type = run[0];
    for (let n = 0; n < length; n++) out[i++] = type;
  }
  return out;
}

export function expandRoadLevels(tiles: TileMap): number[] {
  const out = new Array<number>(tiles.width * tiles.height);
  let i = 0;
  for (const run of tiles.runs) {
    const length = run[run.length - 1] as number;
    const roadLevel = run.length >= 4 ? (run[2] as number) : 0;
    for (let n = 0; n < length; n++) out[i++] = roadLevel;
  }
  return out;
}

export function expandDistricts(tiles: TileMap): string[] {
  const out = new Array<string>(tiles.width * tiles.height);
  let i = 0;
  for (const run of tiles.runs) {
    const length = run[run.length - 1] as number;
    const district = run.length >= 2 ? String(run[1]) : "unknown";
    for (let n = 0; n < length; n++) out[i++] = district;
  }
  return out;
}

export function WorldProps({ tiles }: { tiles: TileMap }) {
  const trees = useMemo(() => {
    const types = expandTiles(tiles);
    const spots: { x: number; z: number; s: number }[] = [];
    for (let y = 0; y < tiles.height; y++) {
      for (let x = 0; x < tiles.width; x++) {
        const t = types[y * tiles.width + x];
        if (t !== "forest" && t !== "park") continue;
        if ((x * 17 + y * 31) % (t === "forest" ? 3 : 7) !== 0) continue;
        spots.push({ x: x + 0.5, z: y + 0.5, s: 0.7 + ((x + y) % 5) * 0.12 });
      }
    }
    return spots.slice(0, 420);
  }, [tiles]);

  return (
    <group>
      {trees.map((tree, i) => (
        <Tree key={i} x={tree.x} z={tree.z} scale={tree.s} />
      ))}
    </group>
  );
}

function Tree({ x, z, scale }: { x: number; z: number; scale: number }) {
  return (
    <group position={[x, 0, z]} scale={scale}>
      <mesh position={[0, 0.28, 0]} castShadow>
        <cylinderGeometry args={[0.06, 0.09, 0.55, 6]} />
        <meshStandardMaterial color="#5C3A22" />
      </mesh>
      <mesh position={[0, 0.75, 0]} castShadow>
        <coneGeometry args={[0.38, 0.7, 7]} />
        <meshStandardMaterial color="#1F6B3A" />
      </mesh>
      <mesh position={[0, 1.05, 0]} castShadow>
        <coneGeometry args={[0.28, 0.5, 7]} />
        <meshStandardMaterial color="#2F8F4E" />
      </mesh>
    </group>
  );
}
