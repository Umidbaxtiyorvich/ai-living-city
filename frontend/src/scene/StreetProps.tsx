import { useMemo } from "react";
import type { TileMap } from "../types";
import { expandRoadLevels, expandTiles } from "./WorldProps";

const ROAD_COLORS: Record<number, string> = {
  1: "#3a3a48", // highway
  2: "#454552", // main avenue
  3: "#505058", // district
  4: "#5a5a62", // local
};

export function StreetProps({ tiles }: { tiles: TileMap }) {
  const props = useMemo(() => {
    const types = expandTiles(tiles);
    const roads = expandRoadLevels(tiles);
    const lights: { x: number; z: number }[] = [];
    const benches: { x: number; z: number }[] = [];

    for (let y = 0; y < tiles.height; y++) {
      for (let x = 0; x < tiles.width; x++) {
        const i = y * tiles.width + x;
        const level = roads[i];
        const type = types[i];
        if (type === "sidewalk" && (x + y) % 11 === 0) {
          benches.push({ x: x + 0.5, z: y + 0.5 });
        }
        if (level > 0 && level <= 2 && (x * 3 + y * 5) % 17 === 0) {
          lights.push({ x: x + 0.5, z: y + 0.5 });
        }
      }
    }
    return { lights: lights.slice(0, 180), benches: benches.slice(0, 80) };
  }, [tiles]);

  return (
    <group>
      {props.lights.map((p, i) => (
        <group key={`l${i}`} position={[p.x, 0, p.z]}>
          <mesh position={[0, 1.8, 0]}>
            <cylinderGeometry args={[0.04, 0.05, 3.6, 6]} />
            <meshStandardMaterial color="#555560" metalness={0.4} roughness={0.5} />
          </mesh>
          <mesh position={[0, 3.5, 0]}>
            <sphereGeometry args={[0.12, 8, 8]} />
            <meshStandardMaterial color="#ffeaa0" emissive="#ffeaa0" emissiveIntensity={0.6} />
          </mesh>
        </group>
      ))}
      {props.benches.map((p, i) => (
        <mesh key={`b${i}`} position={[p.x, 0.25, p.z]}>
          <boxGeometry args={[0.8, 0.2, 0.35]} />
          <meshStandardMaterial color="#6b4f3a" />
        </mesh>
      ))}
    </group>
  );
}

export function roadColorForLevel(level: number): string | null {
  return ROAD_COLORS[level] ?? null;
}
