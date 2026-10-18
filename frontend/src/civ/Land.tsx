import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import {
  BufferGeometry,
  CanvasTexture,
  Color,
  ConeGeometry,
  CylinderGeometry,
  DodecahedronGeometry,
  DoubleSide,
  IcosahedronGeometry,
  InstancedMesh,
  LinearFilter,
  MeshStandardMaterial,
  Object3D,
  PlaneGeometry,
  Vector2,
} from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { act, useCiv } from "./store";
import { surface } from "./textures";

/** Tile under the pointer, read by the building ghost. */
export const hover = { x: 0, y: 0, active: false };

function hash(n: number): number {
  let h = Math.imul(n ^ 0x9e3779b9, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967295;
}

/**
 * Splat weights per terrain code: A = [grass, forest floor, soil], B = [rock, water, sand].
 * Only RGB is used — canvas pixels are premultiplied, so a weight kept in alpha
 * would wipe out the colour channels next to it. Water sits in B's green
 * channel because that is the one a three.js alpha map reads.
 */
const WEIGHTS: Record<string, [number, number, number, number, number, number]> = {
  g: [255, 0, 0, 0, 0, 0],
  F: [255, 0, 30, 0, 0, 0],
  f: [60, 255, 0, 0, 0, 0],
  p: [0, 0, 255, 0, 0, 0],
  P: [40, 0, 255, 0, 0, 0],
  b: [0, 0, 255, 0, 0, 0],
  r: [0, 0, 40, 255, 0, 0],
  s: [0, 0, 0, 0, 0, 255],
  w: [0, 0, 0, 0, 255, 160],
};
const PIXELS = 4;

function splatMaterial(splatA: CanvasTexture, splatB: CanvasTexture): MeshStandardMaterial {
  const material = new MeshStandardMaterial({ roughness: 0.95, metalness: 0, map: splatA });
  material.normalMap = surface("leafy_grass_nor", 40, false);
  material.normalScale = new Vector2(0.6, 0.6);
  const uniforms = {
    splatB: { value: splatB },
    tGrass: { value: surface("leafy_grass_diff") },
    tForest: { value: surface("forest_floor_diff") },
    tSoil: { value: surface("dirt_floor_diff") },
    tRock: { value: surface("rocky_terrain_02_diff") },
    tSand: { value: surface("coast_sand_01_diff") },
    uRepeat: { value: 40.0 },
  };
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <map_pars_fragment>",
        `#include <map_pars_fragment>
uniform sampler2D splatB, tGrass, tForest, tSoil, tRock, tSand;
uniform float uRepeat;
vec3 layer(sampler2D t, vec2 uv) {
  // Two scales blended hide the tiling of a repeated photograph.
  vec3 near = texture2D(t, uv).rgb;
  vec3 far = texture2D(t, uv * 0.23 + vec2(0.37, 0.11)).rgb;
  return mix(near, far, 0.35);
}`,
      )
      .replace(
        "#include <map_fragment>",
        `vec4 sa = texture2D(map, vMapUv);
vec4 sb = texture2D(splatB, vMapUv);
vec2 tuv = vMapUv * uRepeat;
// The meadow photo is late-summer; lift it towards spring green.
vec3 grass = layer(tGrass, tuv) * vec3(0.86, 1.08, 0.78);
vec3 c = grass * sa.r + layer(tForest, tuv) * sa.g + layer(tSoil, tuv) * sa.b
       + layer(tRock, tuv) * sb.r + layer(tSand, tuv) * sb.b;
float w = sa.r + sa.g + sa.b + sb.r + sb.b + 1e-4;
c /= w;
c = mix(c, vec3(0.03, 0.12, 0.16), sb.g * 0.85);
diffuseColor.rgb *= c;`,
      );
  };
  return material;
}

/** The whole map: one plane, photographic ground blended by terrain. */
export function Ground() {
  const width = useCiv((s) => s.width);
  const height = useCiv((s) => s.height);
  const terrain = useCiv((s) => s.terrain);
  const version = useCiv((s) => s.terrainVersion);

  const { canvasA, canvasB, splatA, splatB, material } = useMemo(() => {
    const make = () => {
      const c = document.createElement("canvas");
      c.width = Math.max(1, width * PIXELS);
      c.height = Math.max(1, height * PIXELS);
      const t = new CanvasTexture(c);
      t.magFilter = LinearFilter;
      t.minFilter = LinearFilter;
      return { c, t };
    };
    const a = make();
    const b = make();
    return { canvasA: a.c, canvasB: b.c, splatA: a.t, splatB: b.t, material: splatMaterial(a.t, b.t) };
  }, [width, height]);

  useEffect(() => {
    if (!terrain || !width) return;
    const ctxA = canvasA.getContext("2d");
    const ctxB = canvasB.getContext("2d");
    if (!ctxA || !ctxB) return;
    const imgA = ctxA.createImageData(width * PIXELS, height * PIXELS);
    const imgB = ctxB.createImageData(width * PIXELS, height * PIXELS);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const w = WEIGHTS[terrain[y * width + x]] ?? WEIGHTS.g;
        for (let py = 0; py < PIXELS; py++) {
          for (let px = 0; px < PIXELS; px++) {
            const o = ((y * PIXELS + py) * width * PIXELS + (x * PIXELS + px)) * 4;
            imgA.data[o] = w[0];
            imgA.data[o + 1] = w[1];
            imgA.data[o + 2] = w[2];
            imgA.data[o + 3] = 255;
            imgB.data[o] = w[3];
            imgB.data[o + 1] = w[4];
            imgB.data[o + 2] = w[5];
            imgB.data[o + 3] = 255;
          }
        }
      }
    }
    ctxA.putImageData(imgA, 0, 0);
    ctxB.putImageData(imgB, 0, 0);
    // Soft borders: meadows fade into sand and soil instead of stepping.
    for (const [ctx, canvas] of [
      [ctxA, canvasA],
      [ctxB, canvasB],
    ] as const) {
      ctx.globalCompositeOperation = "copy";
      ctx.filter = "blur(2.2px)";
      ctx.drawImage(canvas, 0, 0);
      ctx.filter = "none";
      ctx.globalCompositeOperation = "source-over";
    }
    splatA.needsUpdate = true;
    splatB.needsUpdate = true;
  }, [terrain, version, width, height, canvasA, canvasB, splatA, splatB]);

  const water = useMemo(
    () =>
      new MeshStandardMaterial({
        color: new Color("#2f6f8f"),
        roughness: 0.08,
        metalness: 0.25,
        transparent: true,
        opacity: 0.82,
        normalMap: surface("waternormals", 18, false),
        normalScale: new Vector2(0.35, 0.35),
        // The water weight lives in the green channel, which alpha maps read.
        alphaMap: splatB,
      }),
    [splatB],
  );
  useFrame((_, dt) => {
    const n = water.normalMap;
    if (n) {
      n.offset.x += dt * 0.006;
      n.offset.y += dt * 0.004;
    }
  });

  if (!width) return null;
  return (
    <group>
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[width / 2 - 0.5, 0, height / 2 - 0.5]}
        receiveShadow
        material={material}
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
      </mesh>
      {/* Lakes and the sea: a moving, glossy surface over the water tiles only. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[width / 2 - 0.5, 0.03, height / 2 - 0.5]} material={water}>
        <planeGeometry args={[width, height]} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[width / 2 - 0.5, -0.06, height / 2 - 0.5]}>
        <planeGeometry args={[width * 5, height * 5]} />
        <meshStandardMaterial color="#1f5a78" roughness={0.12} metalness={0.3} />
      </mesh>
    </group>
  );
}

// -- vegetation geometry -------------------------------------------------------

function jitter(geometry: BufferGeometry, amount: number, seed: number): BufferGeometry {
  const pos = geometry.getAttribute("position");
  for (let i = 0; i < pos.count; i++) {
    const k = 1 + (hash(seed + i * 7) - 0.5) * amount;
    pos.setXYZ(i, pos.getX(i) * k, pos.getY(i) * (1 + (hash(seed + i * 13) - 0.5) * amount * 0.6), pos.getZ(i) * k);
  }
  geometry.computeVertexNormals();
  return geometry;
}

/** A broadleaf crown: a cluster of lumpy spheres. */
function broadleafCrown(): BufferGeometry {
  const blobs: [number, number, number, number][] = [
    [0, 0.0, 0, 0.36],
    [0.2, -0.05, 0.08, 0.26],
    [-0.18, -0.02, -0.1, 0.27],
    [0.04, 0.17, -0.06, 0.25],
    [-0.08, -0.08, 0.2, 0.22],
  ];
  const parts = blobs.map(([x, y, z, r], i) => {
    const g = jitter(new IcosahedronGeometry(r, 2), 0.28, i * 101);
    g.translate(x, y, z);
    return g;
  });
  return mergeGeometries(parts) ?? new IcosahedronGeometry(0.4, 1);
}

/** A conifer: stacked, slightly ragged cones. */
function coniferCrown(): BufferGeometry {
  const parts: BufferGeometry[] = [];
  for (let i = 0; i < 4; i++) {
    const r = 0.34 - i * 0.07;
    const g = jitter(new ConeGeometry(r, 0.42, 9, 2).toNonIndexed(), 0.18, i * 53);
    g.translate(0, -0.25 + i * 0.2, 0);
    parts.push(g);
  }
  return mergeGeometries(parts) ?? new ConeGeometry(0.3, 1, 8);
}

/** Crossed blades for grass tufts. */
function tuftGeometry(): BufferGeometry {
  const a = new PlaneGeometry(0.22, 0.14);
  const b = new PlaneGeometry(0.22, 0.14);
  b.rotateY(Math.PI / 2);
  const merged = mergeGeometries([a, b]) ?? a;
  merged.translate(0, 0.07, 0);
  return merged;
}

function bladeTexture(): CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 64;
  c.height = 64;
  const ctx = c.getContext("2d");
  if (ctx) {
    for (let i = 0; i < 26; i++) {
      const x = 4 + hash(i * 3) * 56;
      const h = 30 + hash(i * 5) * 34;
      const lean = (hash(i * 7) - 0.5) * 14;
      ctx.strokeStyle = `rgb(${70 + hash(i) * 50}, ${120 + hash(i + 1) * 60}, ${40 + hash(i + 2) * 30})`;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x, 64);
      ctx.quadraticCurveTo(x + lean * 0.3, 64 - h * 0.6, x + lean, 64 - h);
      ctx.stroke();
    }
  }
  return new CanvasTexture(c);
}

/** Foliage: hundreds of small leaves in mixed greens with dark gaps between them. */
function foliageTexture(needles: boolean): CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 256;
  const ctx = c.getContext("2d");
  if (ctx) {
    ctx.fillStyle = needles ? "#1d3a22" : "#24451c";
    ctx.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 1400; i++) {
      const x = hash(i * 3 + 1) * 256;
      const y = hash(i * 5 + 2) * 256;
      const light = hash(i * 7 + 3);
      const g = Math.round(90 + light * 110);
      ctx.fillStyle = needles
        ? `rgb(${Math.round(30 + light * 30)}, ${Math.round(g * 0.75)}, ${Math.round(40 + light * 30)})`
        : `rgb(${Math.round(50 + light * 60)}, ${g}, ${Math.round(30 + light * 30)})`;
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(hash(i * 11) * Math.PI);
      ctx.beginPath();
      if (needles) ctx.fillRect(-1, -5, 2, 10);
      else ctx.ellipse(0, 0, 3.5, 6, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }
  const t = new CanvasTexture(c);
  t.wrapS = t.wrapT = 1000; // RepeatWrapping
  t.repeat.set(2, 2);
  t.colorSpace = "srgb";
  return t;
}

const MAX_TREES = 6000;
const MAX_ROCKS = 2500;
const MAX_BUSHES = 1500;
const MAX_TUFTS = 5000;

/** Trees, boulders, bushes and grass — all instanced, a handful of draw calls. */
export function Nature() {
  const width = useCiv((s) => s.width);
  const terrain = useCiv((s) => s.terrain);
  const resources = useCiv((s) => s.resources);
  const settlementKey = useCiv((s) => s.settlements.map((t) => `${t.x},${t.y}`).join(";"));
  const trunks = useRef<InstancedMesh>(null);
  const broad = useRef<InstancedMesh>(null);
  const pines = useRef<InstancedMesh>(null);
  const rocks = useRef<InstancedMesh>(null);
  const bushes = useRef<InstancedMesh>(null);
  const tufts = useRef<InstancedMesh>(null);

  const assets = useMemo(() => {
    const trunk = new CylinderGeometry(0.035, 0.07, 0.6, 7);
    trunk.translate(0, 0.3, 0);
    const rockGeo = jitter(new DodecahedronGeometry(0.5, 1), 0.35, 7);
    const bushGeo = jitter(new IcosahedronGeometry(0.16, 1), 0.3, 11);
    return {
      trunk,
      bark: new MeshStandardMaterial({ map: surface("bark_brown_01_diff", 1), roughness: 0.95 }),
      leaves: new MeshStandardMaterial({ roughness: 0.8, map: foliageTexture(false) }),
      needles: new MeshStandardMaterial({ roughness: 0.85, map: foliageTexture(true) }),
      broadGeo: broadleafCrown(),
      pineGeo: coniferCrown(),
      rock: new MeshStandardMaterial({ map: surface("rocky_terrain_02_diff", 1), roughness: 0.92 }),
      rockGeo,
      bush: new MeshStandardMaterial({ roughness: 0.85, color: "#4f7a3a" }),
      bushGeo,
      blade: new MeshStandardMaterial({ map: bladeTexture(), alphaTest: 0.4, side: DoubleSide, roughness: 0.9 }),
      tuftGeo: tuftGeometry(),
    };
  }, []);

  useLayoutEffect(() => {
    const t = trunks.current;
    const b = broad.current;
    const c = pines.current;
    if (!t || !b || !c || !width) return;
    const dummy = new Object3D();
    const colour = new Color();
    const count = Math.min(MAX_TREES, resources.trees.length);
    let nb = 0;
    let nc = 0;
    for (let n = 0; n < count; n++) {
      const i = resources.trees[n];
      const size = 0.55 + (resources.tree_size[n] ?? 1) * 0.75;
      const x = (i % width) + (hash(i) - 0.5) * 0.55;
      const z = Math.floor(i / width) + (hash(i + 7) - 0.5) * 0.55;
      const tall = 0.8 + hash(i + 3) * 0.6;
      const conifer = hash(i + 17) < 0.38;
      dummy.position.set(x, 0, z);
      dummy.rotation.set(0, hash(i + 11) * 6.28, 0);
      dummy.scale.set(size, size * tall * (conifer ? 1.25 : 1), size);
      dummy.updateMatrix();
      t.setMatrixAt(n, dummy.matrix);
      dummy.position.set(x, size * tall * (conifer ? 0.62 : 0.66), z);
      dummy.scale.set(size * (0.9 + hash(i + 5) * 0.35), size * tall * (conifer ? 1.35 : 1.05), size * (0.9 + hash(i + 9) * 0.35));
      dummy.updateMatrix();
      const shade = hash(i + 13);
      if (conifer) {
        c.setMatrixAt(nc, dummy.matrix);
        colour.setRGB(0.85 + shade * 0.15, 0.85 + shade * 0.15, 0.85 + shade * 0.15);
        c.setColorAt(nc++, colour);
      } else {
        b.setMatrixAt(nb, dummy.matrix);
        // Some trees a little yellower, some bluer — no two alike.
        colour.setRGB(0.85 + shade * 0.3, 0.95 + shade * 0.1, 0.8 + (1 - shade) * 0.2);
        b.setColorAt(nb++, colour);
      }
    }
    t.count = count;
    b.count = nb;
    c.count = nc;
    for (const m of [t, b, c]) {
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
      m.computeBoundingSphere();
    }
  }, [resources, width]);

  useLayoutEffect(() => {
    const r = rocks.current;
    if (!r || !width || !terrain) return;
    const dummy = new Object3D();
    let n = 0;
    for (let i = 0; i < terrain.length && n < MAX_ROCKS; i++) {
      if (terrain[i] !== "r") continue;
      const s = 0.4 + hash(i + 21) * 0.55;
      dummy.position.set((i % width) + (hash(i) - 0.5) * 0.4, s * 0.12, Math.floor(i / width) + (hash(i + 1) - 0.5) * 0.4);
      dummy.rotation.set(hash(i + 2), hash(i + 3) * 6, hash(i + 4));
      dummy.scale.set(s, s * 0.55, s * (0.8 + hash(i + 5) * 0.4));
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
      dummy.position.set((i % width) + (hash(i + 31) - 0.5) * 0.5, 0.1, Math.floor(i / width) + (hash(i + 32) - 0.5) * 0.5);
      dummy.scale.set(0.9 + hash(i + 33) * 0.5, 0.7 + hash(i + 34) * 0.4, 0.9 + hash(i + 35) * 0.5);
      dummy.updateMatrix();
      b.setMatrixAt(n, dummy.matrix);
    }
    b.count = count;
    b.instanceMatrix.needsUpdate = true;
    b.computeBoundingSphere();
  }, [resources, width]);

  // Grass tufts where people live, so close-ups look like a meadow, not a carpet.
  useLayoutEffect(() => {
    const g = tufts.current;
    if (!g || !width || !terrain) return;
    const dummy = new Object3D();
    const centres = settlementKey ? settlementKey.split(";").map((p) => p.split(",").map(Number)) : [];
    let n = 0;
    for (const [sx, sy] of centres) {
      for (let dy = -22; dy <= 22 && n < MAX_TUFTS; dy++) {
        for (let dx = -22; dx <= 22 && n < MAX_TUFTS; dx++) {
          const x = sx + dx;
          const y = sy + dy;
          if (x < 0 || y < 0 || x >= width) continue;
          const i = y * width + x;
          const code = terrain[i];
          if (code !== "g" && code !== "F") continue;
          for (let k = 0; k < 2 && n < MAX_TUFTS; k++) {
            if (hash(i * 5 + k) < 0.35) continue;
            dummy.position.set(x + (hash(i * 3 + k) - 0.5), 0, y + (hash(i * 7 + k) - 0.5));
            dummy.rotation.set(0, hash(i + k) * 6.28, 0);
            dummy.scale.setScalar(0.7 + hash(i * 11 + k) * 0.8);
            dummy.updateMatrix();
            g.setMatrixAt(n++, dummy.matrix);
          }
        }
      }
    }
    g.count = n;
    g.instanceMatrix.needsUpdate = true;
    g.computeBoundingSphere();
  }, [terrain, width, settlementKey]);

  return (
    <group>
      <instancedMesh ref={trunks} args={[assets.trunk, assets.bark, MAX_TREES]} castShadow receiveShadow frustumCulled={false} />
      <instancedMesh ref={broad} args={[assets.broadGeo, assets.leaves, MAX_TREES]} castShadow receiveShadow frustumCulled={false} />
      <instancedMesh ref={pines} args={[assets.pineGeo, assets.needles, MAX_TREES]} castShadow receiveShadow frustumCulled={false} />
      <instancedMesh ref={rocks} args={[assets.rockGeo, assets.rock, MAX_ROCKS]} castShadow receiveShadow frustumCulled={false} />
      <instancedMesh ref={bushes} args={[assets.bushGeo, assets.bush, MAX_BUSHES]} castShadow frustumCulled={false} />
      <instancedMesh ref={tufts} args={[assets.tuftGeo, assets.blade, MAX_TUFTS]} frustumCulled={false} />
    </group>
  );
}
