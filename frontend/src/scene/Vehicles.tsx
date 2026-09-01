import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Group } from "three";
import type { TileMap } from "../types";
import { expandRoadLevels, expandTiles } from "./WorldProps";

type Lane = {
  key: string;
  x: number;
  z: number;
  axis: "x" | "z";
  dir: 1 | -1;
  speed: number;
  color: string;
  phase: number;
};

export function Vehicles({ tiles }: { tiles: TileMap }) {
  const lanes = useMemo(() => collectLanes(tiles), [tiles]);
  const root = useRef<Group>(null);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const group = root.current;
    if (!group) return;
    group.children.forEach((child, i) => {
      const lane = lanes[i];
      if (!lane) return;
      const span = lane.axis === "x" ? tiles.width : tiles.height;
      const offset = ((t * lane.speed + lane.phase) % span) * lane.dir;
      const baseX = lane.axis === "x" ? lane.x + offset : lane.x;
      const baseZ = lane.axis === "z" ? lane.z + offset : lane.z;
      child.position.set(baseX, 0.12, baseZ);
      child.rotation.y = lane.axis === "x" ? (lane.dir > 0 ? 0 : Math.PI) : lane.dir > 0 ? Math.PI / 2 : -Math.PI / 2;
    });
  });

  if (!lanes.length) return null;

  return (
    <group ref={root}>
      {lanes.map((lane) => (
        <group key={lane.key}>
          <mesh castShadow position={[0, 0.08, 0]}>
            <boxGeometry args={[0.42, 0.12, 0.22]} />
            <meshStandardMaterial color={lane.color} roughness={0.45} metalness={0.25} />
          </mesh>
          <mesh position={[0.14, 0.1, 0]}>
            <boxGeometry args={[0.12, 0.08, 0.18]} />
            <meshStandardMaterial color="#1a2230" />
          </mesh>
        </group>
      ))}
    </group>
  );
}

function collectLanes(tiles: TileMap): Lane[] {
  const types = expandTiles(tiles);
  const levels = expandRoadLevels(tiles);
  const colors = ["#c0392b", "#2980b9", "#27ae60", "#f39c12", "#8e44ad", "#ecf0f1"];
  const out: Lane[] = [];
  const step = tiles.width > 120 ? 3 : 2;

  for (let y = 0; y < tiles.height; y += step) {
    for (let x = 0; x < tiles.width; x += step) {
      const i = y * tiles.width + x;
      if (types[i] !== "road") continue;
      const level = levels[i] || 3;
      if (level > 2) continue;
      if ((x * 7 + y * 11) % 5 !== 0) continue;
      const axis: "x" | "z" = x % 2 === 0 ? "x" : "z";
      out.push({
        key: `${x}-${y}`,
        x: x + 0.5,
        z: y + 0.5,
        axis,
        dir: (x + y) % 2 === 0 ? 1 : -1,
        speed: level === 1 ? 2.8 : 1.6,
        color: colors[out.length % colors.length],
        phase: (x * 0.37 + y * 0.53) % 8,
      });
      if (out.length >= 48) return out;
    }
  }
  return out;
}
