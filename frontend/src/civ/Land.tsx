import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import {
  CanvasTexture,
  Color,
  InstancedMesh,
  LinearFilter,
  Object3D,
  SRGBColorSpace,
} from "three";
import type { ThreeEvent } from "@react-three/fiber";
import { act, useCiv } from "./store";

/** Tile under the pointer, read by the building ghost. */
export const hover = { x: 0, y: 0, active: false };

/** Base colour per terrain code (see backend civ/world.py TERRAIN_CODE). */
const GROUND: Record<string, [number, number, number]> = {
  w: [46, 104, 150],
  s: [214, 196, 146],
  g: [112, 156, 74],
  f: [70, 112, 52],
  r: [128, 124, 116],
  F: [128, 166, 70],
  p: [138, 104, 66],
  P: [172, 146, 108],
  b: [160, 150, 128],
};

function hash(n: number): number {
  let h = Math.imul(n ^ 0x9e3779b9, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967295;
}

const PIXELS = 4;

/** The whole map is one textured plane: one draw call however large the land. */
export function Ground() {
  const width = useCiv((s) => s.width);
  const height = useCiv((s) => s.height);
  const terrain = useCiv((s) => s.terrain);
  const version = useCiv((s) => s.terrainVersion);

  const { canvas, texture } = useMemo(() => {
    const c = document.createElement("canvas");
    c.width = Math.max(1, width * PIXELS);
    c.height = Math.max(1, height * PIXELS);
    const t = new CanvasTexture(c);
    t.colorSpace = SRGBColorSpace;
    t.magFilter = LinearFilter;
    t.minFilter = LinearFilter;
    t.anisotropy = 4;
    return { canvas: c, texture: t };
  }, [width, height]);

  useEffect(() => {
    if (!terrain || !width) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const image = ctx.createImageData(width * PIXELS, height * PIXELS);
    const data = image.data;
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const i = y * width + x;
        const code = terrain[i] ?? "g";
        const base = GROUND[code] ?? GROUND.g;
        for (let py = 0; py < PIXELS; py++) {
          for (let px = 0; px < PIXELS; px++) {
            // Per-pixel speckle makes grass and soil read as texture, not tiles.
            const n = hash(i * 16 + py * PIXELS + px);
            const k = code === "w" ? 0.92 + n * 0.12 : 0.86 + n * 0.24;
            const o = ((y * PIXELS + py) * width * PIXELS + (x * PIXELS + px)) * 4;
            data[o] = Math.min(255, base[0] * k);
            data[o + 1] = Math.min(255, base[1] * k);
            data[o + 2] = Math.min(255, base[2] * k);
            data[o + 3] = 255;
          }
        }
      }
    }
    ctx.putImageData(image, 0, 0);
    // Soften the tile grid so coasts and fields have edges, not stairs.
    ctx.filter = "blur(1.2px)";
    ctx.drawImage(canvas, 0, 0);
    ctx.filter = "none";
    texture.needsUpdate = true;
  }, [terrain, version, width, height, canvas, texture]);

  if (!width) return null;
  return (
    <group>
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[width / 2 - 0.5, 0, height / 2 - 0.5]}
        receiveShadow
        onPointerMove={(event: ThreeEvent<PointerEvent>) => {
          hover.x = Math.round(event.point.x);
          hover.y = Math.round(event.point.z);
          hover.active = true;
        }}
        onPointerOut={() => {
          hover.active = false;
        }}
        onClick={(event: ThreeEvent<MouseEvent>) => {
          // A drag to orbit the camera is not a click on the land.
          if (event.delta > 6) return;
          const x = Math.round(event.point.x);
          const y = Math.round(event.point.z);
          const state = useCiv.getState();
          if (state.placing) {
            event.stopPropagation();
            const kind = state.placing;
            void act({ action: "build", kind, x, y, creative: state.creative }).then((result) => {
              if (result.ok) state.setPlacing(null);
            });
            return;
          }
          if (state.playerId != null) {
            void act({ action: "goto", x, y });
          }
        }}
      >
        <planeGeometry args={[width, height]} />
        <meshStandardMaterial map={texture} roughness={0.95} metalness={0} />
      </mesh>
      {/* The sea beyond the island's edge. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[width / 2 - 0.5, -0.04, height / 2 - 0.5]}>
        <planeGeometry args={[width * 4, height * 4]} />
        <meshStandardMaterial color="#2a6189" roughness={0.3} metalness={0.1} />
      </mesh>
    </group>
  );
}

const MAX_TREES = 6000;
const MAX_ROCKS = 2500;
const MAX_BUSHES = 1500;

/** Trees, boulders and bushes — instanced, so thousands cost a handful of draw calls. */
export function Nature() {
  const width = useCiv((s) => s.width);
  const terrain = useCiv((s) => s.terrain);
  const resources = useCiv((s) => s.resources);
  const trunks = useRef<InstancedMesh>(null);
  const crowns = useRef<InstancedMesh>(null);
  const rocks = useRef<InstancedMesh>(null);
  const bushes = useRef<InstancedMesh>(null);

  useLayoutEffect(() => {
    const t = trunks.current;
    const c = crowns.current;
    if (!t || !c || !width) return;
    const dummy = new Object3D();
    const colour = new Color();
    const count = Math.min(MAX_TREES, resources.trees.length);
    for (let n = 0; n < count; n++) {
      const i = resources.trees[n];
      const size = 0.45 + (resources.tree_size[n] ?? 1) * 0.65;
      const x = (i % width) + (hash(i) - 0.5) * 0.5;
      const z = Math.floor(i / width) + (hash(i + 7) - 0.5) * 0.5;
      const tall = 0.7 + hash(i + 3) * 0.5;
      dummy.position.set(x, 0.25 * size * tall, z);
      dummy.rotation.set(0, hash(i + 11) * 6.28, 0);
      dummy.scale.set(size, size * tall, size);
      dummy.updateMatrix();
      t.setMatrixAt(n, dummy.matrix);
      dummy.position.set(x, 0.62 * size * tall + 0.2 * size, z);
      dummy.scale.set(size * (0.9 + hash(i + 5) * 0.3), size * tall * 1.1, size * (0.9 + hash(i + 9) * 0.3));
      dummy.updateMatrix();
      c.setMatrixAt(n, dummy.matrix);
      const shade = hash(i + 13);
      colour.setRGB(0.16 + shade * 0.1, 0.36 + shade * 0.16, 0.14 + shade * 0.06);
      c.setColorAt(n, colour);
    }
    t.count = count;
    c.count = count;
    t.instanceMatrix.needsUpdate = true;
    c.instanceMatrix.needsUpdate = true;
    if (c.instanceColor) c.instanceColor.needsUpdate = true;
    t.computeBoundingSphere();
    c.computeBoundingSphere();
  }, [resources, width]);

  useLayoutEffect(() => {
    const r = rocks.current;
    if (!r || !width || !terrain) return;
    const dummy = new Object3D();
    let n = 0;
    for (let i = 0; i < terrain.length && n < MAX_ROCKS; i++) {
      if (terrain[i] !== "r") continue;
      const s = 0.35 + hash(i + 21) * 0.45;
      dummy.position.set((i % width) + (hash(i) - 0.5) * 0.4, s * 0.25, Math.floor(i / width) + (hash(i + 1) - 0.5) * 0.4);
      dummy.rotation.set(hash(i + 2), hash(i + 3) * 6, hash(i + 4));
      dummy.scale.set(s, s * 0.7, s * (0.8 + hash(i + 5) * 0.4));
      dummy.updateMatrix();
      r.setMatrixAt(n++, dummy.matrix);
    }
    r.count = n;
    r.instanceMatrix.needsUpdate = true;
    r.computeBoundingSphere();
  }, [terrain, width]);

  useLayoutEffect(() => {
    const b = bushes.current;
    if (!b || !width) return;
    const dummy = new Object3D();
    const count = Math.min(MAX_BUSHES, resources.bushes.length);
    for (let n = 0; n < count; n++) {
      const i = resources.bushes[n];
      dummy.position.set((i % width) + (hash(i + 31) - 0.5) * 0.5, 0.12, Math.floor(i / width) + (hash(i + 32) - 0.5) * 0.5);
      dummy.scale.setScalar(0.7 + hash(i + 33) * 0.4);
      dummy.updateMatrix();
      b.setMatrixAt(n, dummy.matrix);
    }
    b.count = count;
    b.instanceMatrix.needsUpdate = true;
    b.computeBoundingSphere();
  }, [resources, width]);

  return (
    <group>
      <instancedMesh ref={trunks} args={[undefined, undefined, MAX_TREES]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[0.05, 0.08, 0.5, 5]} />
        <meshStandardMaterial color="#5a3d26" roughness={0.9} />
      </instancedMesh>
      <instancedMesh ref={crowns} args={[undefined, undefined, MAX_TREES]} castShadow frustumCulled={false}>
        <icosahedronGeometry args={[0.32, 0]} />
        <meshStandardMaterial roughness={0.85} flatShading />
      </instancedMesh>
      <instancedMesh ref={rocks} args={[undefined, undefined, MAX_ROCKS]} castShadow frustumCulled={false}>
        <dodecahedronGeometry args={[0.5, 0]} />
        <meshStandardMaterial color="#8d8a84" roughness={0.95} flatShading />
      </instancedMesh>
      <instancedMesh ref={bushes} args={[undefined, undefined, MAX_BUSHES]} frustumCulled={false}>
        <icosahedronGeometry args={[0.17, 0]} />
        <meshStandardMaterial color="#3f7a34" emissive="#5a1010" emissiveIntensity={0.25} roughness={0.8} flatShading />
      </instancedMesh>
    </group>
  );
}
