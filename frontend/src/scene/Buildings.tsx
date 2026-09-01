import type { BuildingView } from "../types";

export function Buildings({
  buildings,
  selectedId,
  onSelect,
}: {
  buildings: BuildingView[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <group>
      {buildings.map((b) => (
        <group
          key={b.id}
          position={[b.x + b.width / 2, 0, b.y + b.height / 2]}
          onClick={(event) => {
            event.stopPropagation();
            onSelect(b.id);
          }}
        >
          <BuildingMesh building={b} selected={selectedId === b.id} />
        </group>
      ))}
    </group>
  );
}

function BuildingMesh({ building: b, selected }: { building: BuildingView; selected: boolean }) {
  const w = b.width * 0.92;
  const d = b.height * 0.92;
  const stories = Math.max(1, b.levels);
  const h = b.type === "park" ? 0.08 : 0.85 * stories * (b.status === "under_construction" ? Math.max(0.25, b.progress) : 1);
  const wall = selected ? "#FFE08A" : wallColor(b.type);
  const roof = roofColor(b.type);

  if (b.type === "park") return <Park w={w} d={d} />;
  if (b.type === "farm") return <Farm w={w} d={d} wall={wall} />;
  if (b.type === "presidential_palace") return <Palace w={w} d={d} h={h} selected={selected} />;
  if (b.type === "apartment" || b.type === "office" || b.type === "city_hall") {
    const minStories =
      b.type === "apartment" ? Math.max(stories, 10 + (b.id % 8)) : Math.max(stories, 6 + (b.id % 5));
    return (
      <TowerBlock
        w={w}
        d={d}
        stories={minStories}
        wall={wall}
        selected={selected}
        seed={b.id}
      />
    );
  }
  if (b.type === "factory" || b.type === "warehouse" || b.type === "power_plant") {
    return <IndustrialBlock w={w} d={d} h={h * 1.3} wall={wall} kind={b.type} />;
  }
  if (b.type === "townhouse") {
    return <TownhouseBlock w={w} d={d} stories={Math.max(2, stories)} wall={wall} roof={roof} />;
  }
  if (b.type === "bus_stop") {
    return (
      <group>
        <mesh position={[0, 0.55, 0]} castShadow>
          <boxGeometry args={[1.1, 1.1, 0.5]} />
          <meshStandardMaterial color="#2a5080" />
        </mesh>
        <mesh position={[0, 0.35, 0]}>
          <boxGeometry args={[0.9, 0.06, 0.35]} />
          <meshStandardMaterial color="#333" />
        </mesh>
      </group>
    );
  }

  return (
    <group>
      <mesh position={[0, h / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial color={wall} roughness={0.72} />
      </mesh>
      <PitchedRoof w={w} d={d} y={h} color={roof} />
      <Windows w={w} d={d} h={h} stories={stories} />
      <mesh position={[0, 0.22, d / 2 + 0.01]} castShadow>
        <boxGeometry args={[0.22, 0.42, 0.04]} />
        <meshStandardMaterial color="#4A3020" />
      </mesh>
      {b.type === "shop" || b.type === "cafe" || b.type === "restaurant" || b.type === "market" ? (
        <mesh position={[0, 0.55, d / 2 + 0.08]} rotation={[-0.4, 0, 0]}>
          <boxGeometry args={[w * 0.9, 0.04, 0.35]} />
          <meshStandardMaterial color="#C41E3A" />
        </mesh>
      ) : null}
      {b.type === "clinic" || b.type === "hospital" ? (
        <mesh position={[0, h * 0.7, d / 2 + 0.03]}>
          <boxGeometry args={[0.28, 0.28, 0.04]} />
          <meshStandardMaterial color="#C05050" />
        </mesh>
      ) : null}
      {b.type === "school" || b.type === "kindergarten" ? (
        <mesh position={[w * 0.4, h + 0.55, 0]}>
          <cylinderGeometry args={[0.02, 0.02, 0.7, 6]} />
          <meshStandardMaterial color="#888" />
        </mesh>
      ) : null}
      {b.status === "under_construction" && (
        <mesh position={[0, h + 0.15, 0]}>
          <boxGeometry args={[w * 0.3, 0.08, d * 0.3]} />
          <meshStandardMaterial color="#C9A227" />
        </mesh>
      )}
    </group>
  );
}

function TowerBlock({
  w,
  d,
  stories,
  wall,
  selected,
  seed,
}: {
  w: number;
  d: number;
  stories: number;
  wall: string;
  selected: boolean;
  seed: number;
}) {
  const floorH = 0.42;
  const totalH = stories * floorH;
  const tint = selected ? "#FFE08A" : wall;
  const accent = seed % 3 === 0 ? "#6a90b8" : seed % 3 === 1 ? "#8a9aa8" : "#a89078";
  return (
    <group>
      <mesh position={[0, totalH / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[w, totalH, d]} />
        <meshStandardMaterial color={tint} roughness={0.45} metalness={0.08} />
      </mesh>
      {Array.from({ length: Math.min(stories, 14) }, (_, i) => (
        <mesh key={i} position={[0, floorH * (i + 0.55), d / 2 + 0.02]}>
          <boxGeometry args={[w * 0.88, floorH * 0.55, 0.03]} />
          <meshStandardMaterial color={accent} emissive="#112233" emissiveIntensity={0.12} />
        </mesh>
      ))}
      <mesh position={[0, totalH + 0.08, 0]}>
        <boxGeometry args={[w * 0.35, 0.12, d * 0.35]} />
        <meshStandardMaterial color="#555" />
      </mesh>
    </group>
  );
}

function TownhouseBlock({
  w,
  d,
  stories,
  wall,
  roof,
}: {
  w: number;
  d: number;
  stories: number;
  wall: string;
  roof: string;
}) {
  const h = stories * 0.75;
  return (
    <group>
      <mesh position={[0, h / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial color={wall} />
      </mesh>
      <PitchedRoof w={w} d={d} y={h} color={roof} />
      <Windows w={w} d={d} h={h} stories={stories} />
    </group>
  );
}

function IndustrialBlock({
  w,
  d,
  h,
  wall,
  kind,
}: {
  w: number;
  d: number;
  h: number;
  wall: string;
  kind: string;
}) {
  return (
    <group>
      <mesh position={[0, h / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial color={wall} roughness={0.82} />
      </mesh>
      {kind === "power_plant" && (
        <mesh position={[w * 0.25, h + 0.45, 0]}>
          <cylinderGeometry args={[0.12, 0.16, 0.9, 8]} />
          <meshStandardMaterial color="#888" />
        </mesh>
      )}
      {kind === "factory" && (
        <mesh position={[0, h + 0.12, -d * 0.2]}>
          <boxGeometry args={[w * 0.25, 0.22, d * 0.25]} />
          <meshStandardMaterial color="#555" />
        </mesh>
      )}
    </group>
  );
}

function PitchedRoof({ w, d, y, color }: { w: number; d: number; y: number; color: string }) {
  return (
    <group position={[0, y, 0]}>
      <mesh rotation={[0, 0, 0.55]} position={[w * 0.18, 0.18, 0]} castShadow>
        <boxGeometry args={[w * 0.72, 0.08, d * 1.04]} />
        <meshStandardMaterial color={color} roughness={0.85} />
      </mesh>
      <mesh rotation={[0, 0, -0.55]} position={[-w * 0.18, 0.18, 0]} castShadow>
        <boxGeometry args={[w * 0.72, 0.08, d * 1.04]} />
        <meshStandardMaterial color={color} roughness={0.85} />
      </mesh>
    </group>
  );
}

function Windows({ w, d, h, stories }: { w: number; d: number; h: number; stories: number }) {
  const cols = Math.max(2, Math.floor(w * 1.6));
  const panes = [];
  for (let story = 0; story < stories; story++) {
    const y = 0.35 + story * (h / stories);
    for (let i = 0; i < cols; i++) {
      const x = -w / 2 + 0.28 + (i * (w - 0.5)) / Math.max(1, cols - 1);
      panes.push(
        <mesh key={`${story}-${i}`} position={[x, y, d / 2 + 0.015]}>
          <boxGeometry args={[0.14, 0.16, 0.02]} />
          <meshStandardMaterial color="#87CEEB" emissive="#223344" emissiveIntensity={0.15} />
        </mesh>,
      );
    }
  }
  return <group>{panes}</group>;
}

function Palace({ w, d, h, selected }: { w: number; d: number; h: number; selected: boolean }) {
  const wall = selected ? "#FFE08A" : "#E8D5A3";
  return (
    <group>
      <mesh position={[0, h / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial color={wall} roughness={0.55} />
      </mesh>
      <mesh position={[0, h + 0.55, 0]} castShadow>
        <sphereGeometry args={[Math.min(w, d) * 0.28, 16, 12]} />
        <meshStandardMaterial color="#C9A227" metalness={0.35} roughness={0.35} />
      </mesh>
    </group>
  );
}

function Park({ w, d }: { w: number; d: number }) {
  return (
    <group>
      <mesh position={[0, 0.04, 0]} receiveShadow>
        <boxGeometry args={[w, 0.06, d]} />
        <meshStandardMaterial color="#2F8F4E" />
      </mesh>
      <mesh position={[0, 0.22, 0]}>
        <cylinderGeometry args={[0.35, 0.4, 0.18, 12]} />
        <meshStandardMaterial color="#8AA0B8" />
      </mesh>
    </group>
  );
}

function Farm({ w, d, wall }: { w: number; d: number; wall: string }) {
  return (
    <group>
      <mesh position={[0, 0.45, -d * 0.2]} castShadow>
        <boxGeometry args={[w * 0.45, 0.9, d * 0.4]} />
        <meshStandardMaterial color={wall} />
      </mesh>
      <PitchedRoof w={w * 0.5} d={d * 0.42} y={0.9} color="#7A3E2A" />
    </group>
  );
}

function wallColor(type: string): string {
  const map: Record<string, string> = {
    house: "#D9B48A",
    townhouse: "#C4A07A",
    apartment: "#B8C4D4",
    city_hall: "#F0EBE3",
    school: "#E8D9B8",
    clinic: "#F5F2EA",
    hospital: "#F2F2F2",
    shop: "#E6C27A",
    market: "#C9A227",
    office: "#9AAFC8",
    factory: "#8A8A90",
    warehouse: "#9A9488",
    power_plant: "#7a7a82",
  };
  return map[type] ?? "#C8B8A0";
}

function roofColor(type: string): string {
  const map: Record<string, string> = {
    house: "#8B3A2A",
    townhouse: "#7A3324",
    apartment: "#6B4033",
    school: "#2C4A7A",
    shop: "#8A2010",
  };
  return map[type] ?? "#6B3A28";
}
