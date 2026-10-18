import { useLayoutEffect, useMemo, useRef } from "react";
import {
  BoxGeometry,
  BufferGeometry,
  Color,
  ConeGeometry,
  CylinderGeometry,
  IcosahedronGeometry,
  InstancedMesh,
  MeshStandardMaterial,
  Object3D,
  PlaneGeometry,
  SphereGeometry,
  DoubleSide,
} from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { surface } from "./textures";

/**
 * A sown field: rows of the crop its farmers chose, growing from shoots to a
 * ripe harvest. One instanced mesh for the plants and one for what they bear,
 * so a field is two draw calls whatever it grows.
 */

function hash(n: number): number {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

function merged(parts: BufferGeometry[]): BufferGeometry {
  return mergeGeometries(parts.map((p) => (p.index ? p.toNonIndexed() : p))) ?? parts[0];
}

/** A clump of grain stalks with ears at the top. */
function grainPlant(): BufferGeometry {
  const parts: BufferGeometry[] = [];
  for (let i = 0; i < 5; i++) {
    const stalk = new BoxGeometry(0.008, 0.26, 0.008);
    stalk.translate((hash(i) - 0.5) * 0.06, 0.13, (hash(i + 9) - 0.5) * 0.06);
    stalk.rotateZ((hash(i + 3) - 0.5) * 0.25);
    parts.push(stalk);
    const ear = new BoxGeometry(0.016, 0.06, 0.016);
    ear.translate((hash(i) - 0.5) * 0.06, 0.28, (hash(i + 9) - 0.5) * 0.06);
    parts.push(ear);
  }
  return merged(parts);
}

/** A tall maize stalk with long leaves. */
function cornPlant(): BufferGeometry {
  const parts: BufferGeometry[] = [];
  const stalk = new CylinderGeometry(0.008, 0.014, 0.5, 5);
  stalk.translate(0, 0.25, 0);
  parts.push(stalk);
  for (let i = 0; i < 4; i++) {
    const leaf = new PlaneGeometry(0.03, 0.22);
    leaf.translate(0, 0.11, 0);
    leaf.rotateZ(0.9);
    leaf.rotateY(i * 1.7);
    leaf.translate(0, 0.12 + i * 0.09, 0);
    parts.push(leaf);
  }
  return merged(parts);
}

/** Low feathery tops of root vegetables. */
function leafyPlant(): BufferGeometry {
  const parts: BufferGeometry[] = [];
  for (let i = 0; i < 6; i++) {
    const frond = new ConeGeometry(0.012, 0.1, 4);
    frond.translate(0, 0.05, 0);
    frond.rotateX((hash(i) - 0.5) * 0.9);
    frond.rotateZ((hash(i + 4) - 0.5) * 0.9);
    parts.push(frond);
  }
  return merged(parts);
}

/** A bushy potato plant. */
function bushPlant(): BufferGeometry {
  const g = new IcosahedronGeometry(0.06, 1);
  g.scale(1.2, 0.7, 1.2);
  g.translate(0, 0.045, 0);
  return g;
}

/** Melon vines spreading over the ground. */
function vinePlant(): BufferGeometry {
  const parts: BufferGeometry[] = [];
  for (let i = 0; i < 4; i++) {
    const leaf = new SphereGeometry(0.035, 6, 4);
    leaf.scale(1.3, 0.35, 1);
    leaf.translate(Math.cos(i * 1.6) * 0.05, 0.012, Math.sin(i * 1.6) * 0.05);
    parts.push(leaf);
  }
  return merged(parts);
}

interface CropLook {
  plant: () => BufferGeometry;
  /** Colour young → ripe. */
  young: string;
  ripe: string;
  fruit?: { geometry: () => BufferGeometry; colour: string; from: number };
  height: number;
}

const CROP_LOOK: Record<string, CropLook> = {
  wheat: { plant: grainPlant, young: "#6f9a3a", ripe: "#d9b55a", height: 1 },
  barley: { plant: grainPlant, young: "#7aa24a", ripe: "#c9a866", height: 0.85 },
  corn: {
    plant: cornPlant,
    young: "#5f9a3a",
    ripe: "#a7a04a",
    height: 1,
    fruit: { geometry: () => { const g = new CylinderGeometry(0.018, 0.014, 0.08, 6); g.translate(0.02, 0.28, 0); g.rotateZ(-0.3); return g; }, colour: "#e6c24a", from: 0.65 },
  },
  carrot: {
    plant: leafyPlant,
    young: "#5ea03a",
    ripe: "#4f8f32",
    height: 1,
    fruit: { geometry: () => { const g = new ConeGeometry(0.014, 0.04, 6); g.rotateX(Math.PI); g.translate(0, 0.005, 0); return g; }, colour: "#e2782a", from: 0.7 },
  },
  potato: {
    plant: bushPlant,
    young: "#4f8a34",
    ripe: "#5d7f36",
    height: 1,
    fruit: { geometry: () => { const g = new SphereGeometry(0.012, 5, 4); g.translate(0.03, 0.09, 0.01); return g; }, colour: "#f4f0e6", from: 0.55 },
  },
  melon: {
    plant: vinePlant,
    young: "#5a9a3a",
    ripe: "#6a8a34",
    height: 1,
    fruit: { geometry: () => { const g = new SphereGeometry(0.05, 10, 8); g.scale(1.3, 0.85, 1); g.translate(0.03, 0.04, 0.02); return g; }, colour: "#e0c252", from: 0.5 },
  },
};

const ROWS = 6;
const PER_ROW = 9;

export function CropField({ crop, growth, w, d }: { crop: string; growth: number; w: number; d: number }) {
  const plants = useRef<InstancedMesh>(null);
  const fruits = useRef<InstancedMesh>(null);
  const look = CROP_LOOK[crop];
  const assets = useMemo(() => {
    if (!look) return null;
    return {
      plant: look.plant(),
      plantMat: new MeshStandardMaterial({ roughness: 0.85, side: DoubleSide }),
      fruit: look.fruit ? look.fruit.geometry() : null,
      fruitMat: look.fruit ? new MeshStandardMaterial({ color: look.fruit.colour, roughness: 0.6 }) : null,
    };
  }, [look]);

  useLayoutEffect(() => {
    if (!look || !assets) return;
    const p = plants.current;
    const f = fruits.current;
    const dummy = new Object3D();
    const stage = Math.max(0.12, growth);
    const colour = new Color(look.young).lerp(new Color(look.ripe), Math.min(1, Math.max(0, (growth - 0.45) / 0.55)));
    if (assets.plantMat.color.getHex() !== colour.getHex()) assets.plantMat.color.copy(colour);
    let n = 0;
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < PER_ROW; c++) {
        const k = r * PER_ROW + c;
        dummy.position.set(-w / 2 + 0.12 + (c / (PER_ROW - 1)) * (w - 0.24) + (hash(k) - 0.5) * 0.05, 0.02, -d / 2 + 0.15 + (r / (ROWS - 1)) * (d - 0.3));
        dummy.rotation.set(0, hash(k + 50) * 6.28, 0);
        const s = (0.8 + hash(k + 99) * 0.35) * look.height;
        dummy.scale.set(s, s * stage, s);
        dummy.updateMatrix();
        p?.setMatrixAt(n, dummy.matrix);
        if (f) {
          const ripe = look.fruit && growth >= look.fruit.from;
          if (ripe) {
            dummy.scale.set(s, s * (crop === "corn" ? stage : 1), s);
            dummy.updateMatrix();
          } else {
            dummy.scale.set(0, 0, 0);
            dummy.updateMatrix();
          }
          f.setMatrixAt(n, dummy.matrix);
        }
        n++;
      }
    }
    if (p) {
      p.count = n;
      p.instanceMatrix.needsUpdate = true;
      p.computeBoundingSphere();
    }
    if (f) {
      f.count = n;
      f.instanceMatrix.needsUpdate = true;
      f.computeBoundingSphere();
    }
  }, [look, assets, growth, w, d, crop]);

  if (!look || !assets) return null;
  return (
    <group>
      <instancedMesh ref={plants} args={[assets.plant, assets.plantMat, ROWS * PER_ROW]} castShadow />
      {assets.fruit && assets.fruitMat && (
        <instancedMesh ref={fruits} args={[assets.fruit, assets.fruitMat, ROWS * PER_ROW]} castShadow />
      )}
    </group>
  );
}

/** Ploughed soil with furrows and a split-rail fence around it. */
export function FieldBed({ w, d }: { w: number; d: number }) {
  const soil = useMemo(() => {
    const m = new MeshStandardMaterial({ map: surface("farm_soil_diff", 1), roughness: 1 });
    return m;
  }, []);
  const wood = useMemo(() => new MeshStandardMaterial({ map: surface("rough_wood_diff", 1), color: "#d8c3a0", roughness: 0.9 }), []);
  const posts: [number, number][] = [];
  const W = w + 0.16;
  const D = d + 0.16;
  for (let i = 0; i <= 4; i++) {
    posts.push([-W / 2 + (i / 4) * W, -D / 2], [-W / 2 + (i / 4) * W, D / 2]);
    if (i > 0 && i < 4) posts.push([-W / 2, -D / 2 + (i / 4) * D], [W / 2, -D / 2 + (i / 4) * D]);
  }
  return (
    <group>
      <mesh material={soil} position={[0, 0.012, 0]} receiveShadow>
        <boxGeometry args={[w + 0.06, 0.024, d + 0.06]} />
      </mesh>
      {Array.from({ length: ROWS }, (_, r) => (
        <mesh key={r} material={soil} position={[0, 0.028, -d / 2 + 0.15 + (r / (ROWS - 1)) * (d - 0.3)]} receiveShadow>
          <boxGeometry args={[w - 0.1, 0.02, 0.07]} />
        </mesh>
      ))}
      {posts.map(([x, z], i) => (
        <mesh key={i} material={wood} position={[x, 0.07, z]} castShadow>
          <boxGeometry args={[0.025, 0.14, 0.025]} />
        </mesh>
      ))}
      {[
        [0, -D / 2, W, 0],
        [0, D / 2, W, 0],
        [-W / 2, 0, D, Math.PI / 2],
        [W / 2, 0, D, Math.PI / 2],
      ].map(([x, z, len, rot], i) => (
        <group key={i}>
          <mesh material={wood} position={[x, 0.1, z]} rotation={[0, rot, 0]} castShadow>
            <boxGeometry args={[len, 0.015, 0.015]} />
          </mesh>
          <mesh material={wood} position={[x, 0.05, z]} rotation={[0, rot, 0]}>
            <boxGeometry args={[len, 0.015, 0.015]} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

export const CROP_NAMES: Record<string, string> = {
  wheat: "Bug'doy",
  barley: "Arpa",
  corn: "Makkajo'xori",
  carrot: "Sabzi",
  potato: "Kartoshka",
  melon: "Qovun",
};
