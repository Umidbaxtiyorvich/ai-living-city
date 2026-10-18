import { memo, useMemo } from "react";
import type { ThreeEvent } from "@react-three/fiber";
import { BoxGeometry, Color, ConeGeometry, CylinderGeometry, MeshStandardMaterial, SphereGeometry } from "three";
import { surface } from "./textures";
import { useCiv, type CivBuilding } from "./store";

// One geometry per primitive and one material per colour, shared by every building.
const GEO = {
  box: new BoxGeometry(1, 1, 1),
  prism: new CylinderGeometry(0.5, 0.5, 1, 3, 1),
  cone: new ConeGeometry(0.5, 1, 8),
  cone4: new ConeGeometry(0.5, 1, 4),
  cyl: new CylinderGeometry(0.5, 0.5, 1, 12),
  dome: new SphereGeometry(0.5, 16, 10, 0, Math.PI * 2, 0, Math.PI / 2),
  log: new CylinderGeometry(0.05, 0.05, 1, 5),
};
const MATS = new Map<string, MeshStandardMaterial>();
// Photographic surfaces: the colour tints the photo, so walls keep each family's hue.
const PLASTER = "plastered_wall_02_diff";
const PLANKS = "weathered_planks_diff";
const THATCHED = "thatch_roof_angled_diff";
const STONEWALL = "stone_wall_diff";
const TILES = "clay_roof_tiles_diff";
const LOGS = "rough_wood_diff";

/** A colour pulled towards white, so a tint does not drown the photo under it. */
function light(colour: string, amount = 0.45): string {
  return `#${new Color(colour).lerp(new Color("#ffffff"), amount).getHexString()}`;
}

function mat(colour: string, emissive?: string, tex?: string): MeshStandardMaterial {
  const key = `${colour}|${emissive ?? ""}|${tex ?? ""}`;
  let m = MATS.get(key);
  if (!m) {
    m = new MeshStandardMaterial({ color: colour, roughness: 0.82, metalness: 0.02 });
    if (tex) m.map = surface(tex, 1);
    if (emissive) {
      m.emissive.set(emissive);
      m.emissiveIntensity = 0.9;
    }
    MATS.set(key, m);
  }
  return m;
}

const WOOD = "#8b5e3c";
const STONE = "#a8a196";
const DARK = "#2b2420";
const WINDOW = "#f2d27a";

function Box({ p, s, c, r = 0, e, t }: { p: [number, number, number]; s: [number, number, number]; c: string; r?: number; e?: string; t?: string }) {
  return <mesh geometry={GEO.box} material={mat(c, e, t)} position={p} scale={s} rotation={[0, r, 0]} castShadow receiveShadow />;
}

/** A gable roof: a triangular prism lying along x. */
function Gable({ y, w, d, h, c, t = TILES }: { y: number; w: number; d: number; h: number; c: string; t?: string }) {
  // A 3-sided cylinder turned so its axis runs along x and one edge points up.
  // Its triangle spans -0.25..+0.5 of the radius-0.5 circle, so the base sits
  // a quarter of the height below the centre.
  const sz = h / 0.75;
  return (
    <mesh
      geometry={GEO.prism}
      material={mat(light(c, 0.35), undefined, t)}
      position={[0, y + 0.25 * sz - 0.01, 0]}
      rotation={[-Math.PI / 2, 0, Math.PI / 2]}
      scale={[(d * 1.12) / 0.866, w * 1.06, sz]}
      castShadow
    />
  );
}

function Windows({ w, d, y, rows = 1, night }: { w: number; d: number; y: number; rows?: number; night: boolean }) {
  const glow = night ? "#a07a20" : undefined;
  const out = [];
  for (let r = 0; r < rows; r++) {
    for (const x of [-w * 0.28, w * 0.28]) {
      out.push(<Box key={`f${r}${x}`} p={[x, y + r * 0.42, d / 2 + 0.01]} s={[0.16, 0.14, 0.02]} c={WINDOW} e={glow} />);
    }
  }
  return <>{out}</>;
}

function Door({ d, c = DARK }: { d: number; c?: string }) {
  return <Box p={[0, 0.13, d / 2 + 0.01]} s={[0.18, 0.26, 0.03]} c={c} />;
}

function Home({ b, night }: { b: CivBuilding; night: boolean }) {
  const w = b.w * 0.82;
  const d = b.h * 0.82;
  switch (b.kind) {
    case "hut":
      return (
        <group>
          <mesh geometry={GEO.cyl} material={mat("#d9c3a0", undefined, PLASTER)} position={[0, 0.16, 0]} scale={[0.62, 0.32, 0.62]} castShadow />
          <mesh geometry={GEO.cone} material={mat("#fff2d0", undefined, THATCHED)} position={[0, 0.5, 0]} scale={[0.82, 0.48, 0.82]} castShadow />
          <Door d={0.6} />
        </group>
      );
    case "cabin":
      return (
        <group>
          <Box p={[0, 0.25, 0]} s={[w, 0.5, d]} c="#e8d2b0" t={PLANKS} />
          <Gable y={0.5} w={w} d={d} h={0.32} c="#fff4d8" t={THATCHED} />
          <Door d={d} />
          <Windows w={w} d={d} y={0.3} night={night} />
          <Box p={[w * 0.32, 0.78, 0]} s={[0.1, 0.3, 0.1]} c={STONE} />
        </group>
      );
    case "mudhouse":
      return (
        <group>
          <Box p={[0, 0.24, 0]} s={[w, 0.48, d]} c={light(b.wall, 0.3)} t={PLASTER} />
          <Box p={[0, 0.5, 0]} s={[w + 0.06, 0.05, d + 0.06]} c="#7a5a3a" />
          {[-0.3, -0.1, 0.1, 0.3].map((x) => (
            <mesh key={x} geometry={GEO.log} material={mat("#6e4a2e")} position={[x * w, 0.45, d / 2 + 0.04]} rotation={[Math.PI / 2, 0, 0]} scale={[1, 0.12, 1]} />
          ))}
          <Door d={d} />
          <Windows w={w} d={d} y={0.3} night={night} />
        </group>
      );
    case "stonehouse":
      return (
        <group>
          <Box p={[0, 0.28, 0]} s={[w, 0.56, d]} c={light(b.wall, 0.55)} t={STONEWALL} />
          <Box p={[0, 0.03, 0]} s={[w + 0.05, 0.06, d + 0.05]} c="#7d776d" />
          <Gable y={0.56} w={w} d={d} h={0.34} c={b.roof} />
          <Door d={d} />
          <Windows w={w} d={d} y={0.34} night={night} />
        </group>
      );
    case "twostory":
      return (
        <group>
          <Box p={[0, 0.45, 0]} s={[w, 0.9, d]} c={light(b.wall, 0.3)} t={PLASTER} />
          <Box p={[0, 0.46, d / 2 + 0.06]} s={[w * 0.9, 0.04, 0.14]} c="#6e4a2e" />
          <Gable y={0.9} w={w} d={d} h={0.38} c={b.roof} />
          <Door d={d} />
          <Windows w={w} d={d} y={0.3} rows={2} night={night} />
        </group>
      );
    case "villa":
      return (
        <group>
          <Box p={[0, 0.4, -d * 0.3]} s={[w, 0.8, d * 0.4]} c={light(b.wall, 0.3)} t={PLASTER} />
          <Box p={[-w * 0.38, 0.3, d * 0.12]} s={[w * 0.24, 0.6, d * 0.5]} c={light(b.wall, 0.3)} t={PLASTER} />
          <Box p={[w * 0.38, 0.3, d * 0.12]} s={[w * 0.24, 0.6, d * 0.5]} c={light(b.wall, 0.3)} t={PLASTER} />
          <Box p={[0, 0.12, d * 0.42]} s={[w, 0.24, 0.06]} c={b.wall} />
          <Box p={[0, 0.83, -d * 0.3]} s={[w + 0.08, 0.06, d * 0.48]} c={light(b.roof, 0.35)} t={TILES} />
          <mesh geometry={GEO.cyl} material={mat("#4f8fb8")} position={[0, 0.03, d * 0.1]} scale={[0.4, 0.04, 0.4]} />
          <mesh geometry={GEO.cone} material={mat("#3f7a34")} position={[w * 0.15, 0.3, d * 0.2]} scale={[0.25, 0.5, 0.25]} />
          <Windows w={w} d={d * 0.4} y={0.5} night={night} />
        </group>
      );
    default:
      return <Box p={[0, 0.25, 0]} s={[w, 0.5, d]} c={b.wall} />;
  }
}

function Civic({ b, night }: { b: CivBuilding; night: boolean }) {
  const w = b.w * 0.86;
  const d = b.h * 0.86;
  switch (b.kind) {
    case "campfire":
      return (
        <group>
          {Array.from({ length: 7 }, (_, i) => {
            const a = (i / 7) * Math.PI * 2;
            return <Box key={i} p={[Math.cos(a) * 0.28, 0.04, Math.sin(a) * 0.28]} s={[0.1, 0.08, 0.1]} c={STONE} r={a} />;
          })}
          <mesh geometry={GEO.cone} material={mat("#ff8a2a", "#ff6a00")} position={[0, 0.2, 0]} scale={[0.22, 0.38, 0.22]} />
          <mesh geometry={GEO.cone} material={mat("#ffd25a", "#ffb000")} position={[0, 0.16, 0]} scale={[0.12, 0.24, 0.12]} />
          {[0, 1.2, 2.4].map((r) => (
            <mesh key={r} geometry={GEO.log} material={mat(WOOD)} position={[0, 0.06, 0]} rotation={[Math.PI / 2, r, 0]} scale={[1, 0.5, 1]} />
          ))}
        </group>
      );
    case "storehouse":
      return (
        <group>
          <Box p={[0, 0.3, 0]} s={[w, 0.6, d]} c="#e8d2b0" t={LOGS} />
          <Gable y={0.6} w={w} d={d} h={0.3} c="#fff4d8" t={THATCHED} />
          <Box p={[0, 0.2, d / 2 + 0.01]} s={[0.4, 0.4, 0.03]} c={DARK} />
        </group>
      );
    case "granary":
      return (
        <group>
          {[-0.28, 0.28].map((x) => (
            <group key={x} position={[x * w, 0, 0]}>
              <mesh geometry={GEO.cyl} material={mat(light(b.wall, 0.3), undefined, PLASTER)} position={[0, 0.4, 0]} scale={[0.55, 0.8, 0.55]} castShadow />
              <mesh geometry={GEO.cone} material={mat("#fff4d8", undefined, THATCHED)} position={[0, 0.95, 0]} scale={[0.66, 0.32, 0.66]} castShadow />
            </group>
          ))}
        </group>
      );
    case "field": {
      const ripe = b.growth;
      const crop = `rgb(${Math.round(90 + ripe * 130)}, ${Math.round(150 + ripe * 40)}, ${Math.round(50 - ripe * 20)})`;
      const rows = [];
      for (let i = 0; i < 6; i++) {
        rows.push(<Box key={i} p={[0, 0.03 + ripe * 0.05, -d / 2 + 0.2 + (i * (d - 0.4)) / 5]} s={[w, 0.06 + ripe * 0.1, 0.16]} c={crop} />);
      }
      return (
        <group>
          <Box p={[0, 0.01, 0]} s={[w + 0.1, 0.02, d + 0.1]} c="#ffffff" t="farm_soil_diff" />
          {rows}
        </group>
      );
    }
    case "well":
      return (
        <group>
          <mesh geometry={GEO.cyl} material={mat(STONE)} position={[0, 0.14, 0]} scale={[0.5, 0.28, 0.5]} castShadow />
          <Box p={[0.2, 0.42, 0]} s={[0.05, 0.56, 0.05]} c={WOOD} />
          <Box p={[-0.2, 0.42, 0]} s={[0.05, 0.56, 0.05]} c={WOOD} />
          <mesh geometry={GEO.cone4} material={mat(b.roof)} position={[0, 0.78, 0]} rotation={[0, Math.PI / 4, 0]} scale={[0.62, 0.22, 0.62]} />
        </group>
      );
    case "market":
      return (
        <group>
          <Box p={[0, 0.02, 0]} s={[w, 0.04, d]} c="#c9b48a" />
          {[[-0.3, -0.3], [0.3, -0.3], [-0.3, 0.3], [0.3, 0.3]].map(([x, z], i) => (
            <group key={i} position={[x * w, 0, z * d]}>
              <Box p={[0, 0.16, 0]} s={[0.5, 0.32, 0.4]} c={WOOD} />
              <mesh geometry={GEO.cone4} material={mat(["#c0392b", "#e0b33a", "#2e86ab", "#7d3c98"][i])} position={[0, 0.5, 0]} rotation={[0, Math.PI / 4, 0]} scale={[0.8, 0.26, 0.8]} castShadow />
            </group>
          ))}
        </group>
      );
    case "temple":
      return (
        <group>
          <Box p={[0, 0.1, 0]} s={[w, 0.2, d]} c="#cfc6b4" />
          <Box p={[0, 0.5, 0]} s={[w * 0.7, 0.6, d * 0.7]} c="#f0e8dc" t={STONEWALL} />
          <mesh geometry={GEO.dome} material={mat("#2f7fb0")} position={[0, 0.8, 0]} scale={[w * 0.55, w * 0.5, w * 0.55]} castShadow />
          <Box p={[0, 0.32, d * 0.36]} s={[0.3, 0.44, 0.03]} c={DARK} />
        </group>
      );
    case "townhall":
      return (
        <group>
          <Box p={[0, 0.08, 0]} s={[w, 0.16, d]} c="#d8d0c0" />
          <Box p={[0, 0.55, -d * 0.1]} s={[w * 0.9, 0.8, d * 0.7]} c={light(b.wall, 0.35)} t={PLASTER} />
          {[-0.36, -0.12, 0.12, 0.36].map((x) => (
            <mesh key={x} geometry={GEO.cyl} material={mat("#efe9dc")} position={[x * w, 0.5, d * 0.36]} scale={[0.1, 0.7, 0.1]} castShadow />
          ))}
          <Gable y={0.95} w={w * 0.9} d={d * 0.9} h={0.3} c={b.roof} />
          <Box p={[0, 1.45, 0]} s={[0.02, 0.4, 0.02]} c="#555" />
          <Box p={[0.12, 1.58, 0]} s={[0.22, 0.13, 0.01]} c="#1eb5e6" />
        </group>
      );
    case "palace":
      return (
        <group>
          <Box p={[0, 0.12, 0]} s={[w, 0.24, d]} c="#e2d8c4" />
          <Box p={[0, 0.7, 0]} s={[w * 0.7, 1.0, d * 0.6]} c={light(b.wall, 0.4)} t={PLASTER} />
          <mesh geometry={GEO.dome} material={mat("#2f8fc0")} position={[0, 1.2, 0]} scale={[1.3, 1.1, 1.3]} castShadow />
          {[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([x, z], i) => (
            <group key={i} position={[x * w * 0.42, 0, z * d * 0.42]}>
              <mesh geometry={GEO.cyl} material={mat(b.wall)} position={[0, 0.8, 0]} scale={[0.32, 1.6, 0.32]} castShadow />
              <mesh geometry={GEO.dome} material={mat("#2f8fc0")} position={[0, 1.6, 0]} scale={[0.36, 0.3, 0.36]} />
            </group>
          ))}
          <Windows w={w * 0.7} d={d * 0.6} y={0.5} rows={2} night={night} />
        </group>
      );
    default: {
      // workshop, healer, school: walled hall with a pitched roof and a sign colour.
      const sign = { workshop: "#8a5a2b", healer: "#2e8b57", school: "#2e6fa8" }[b.kind] ?? "#777";
      return (
        <group>
          <Box p={[0, 0.3, 0]} s={[w, 0.6, d]} c={light(b.wall, 0.3)} t={PLASTER} />
          <Gable y={0.6} w={w} d={d} h={0.3} c={b.roof} />
          <Box p={[0, 0.5, d / 2 + 0.02]} s={[0.36, 0.12, 0.02]} c={sign} />
          <Door d={d} />
          <Windows w={w} d={d} y={0.32} night={night} />
        </group>
      );
    }
  }
}

/** Timber frame and a part-built shell, rising with progress. */
function Site({ b }: { b: CivBuilding }) {
  const w = b.w * 0.84;
  const d = b.h * 0.84;
  const height = 0.55 * b.levels;
  const built = Math.max(0.04, height * b.progress);
  const posts: [number, number][] = [[-1, -1], [1, -1], [-1, 1], [1, 1]];
  return (
    <group>
      <Box p={[0, 0.015, 0]} s={[w + 0.1, 0.03, d + 0.1]} c="#9b8a6a" />
      <Box p={[0, built / 2, 0]} s={[w * 0.96, built, d * 0.96]} c={b.kind === "field" ? "#6b4b2c" : b.wall} />
      {b.kind !== "field" &&
        posts.map(([x, z], i) => (
          <mesh key={i} geometry={GEO.log} material={mat("#c8a36a")} position={[(x * w) / 2, height / 2 + 0.05, (z * d) / 2]} scale={[1, height + 0.1, 1]} castShadow />
        ))}
      <Box p={[w * 0.6, 0.06, 0]} s={[0.3, 0.12, 0.2]} c={WOOD} />
    </group>
  );
}

const Structure = memo(function Structure({ b, night, selected }: { b: CivBuilding; night: boolean; selected: boolean }) {
  const cx = b.x + (b.w - 1) / 2;
  const cz = b.y + (b.h - 1) / 2;
  const onClick = (event: ThreeEvent<MouseEvent>) => {
    event.stopPropagation();
    useCiv.getState().select(-b.id);
  };
  return (
    <group position={[cx, 0, cz]} onClick={onClick}>
      {!b.complete ? <Site b={b} /> : b.category === "home" ? <Home b={b} night={night} /> : <Civic b={b} night={night} />}
      {selected && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
          <ringGeometry args={[Math.max(b.w, b.h) * 0.62, Math.max(b.w, b.h) * 0.7, 32]} />
          <meshBasicMaterial color="#ffe08a" />
        </mesh>
      )}
    </group>
  );
});

export function Structures() {
  const buildings = useCiv((s) => s.buildings);
  const night = useCiv((s) => s.time?.night ?? false);
  const selected = useCiv((s) => s.selected);
  const list = useMemo(() => buildings, [buildings]);
  return (
    <group>
      {list.map((b) => (
        <Structure key={b.id} b={b} night={night} selected={selected === -b.id} />
      ))}
    </group>
  );
}
