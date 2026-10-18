import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import {
  AnimationAction,
  AnimationClip,
  AnimationMixer,
  Box3,
  Color,
  Group,
  LoopRepeat,
  Mesh,
  MeshStandardMaterial,
  type Material,
  type Object3D,
} from "three";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";
import { bodies, realIds } from "./People";
import { useCiv, type Looks } from "./store";

/**
 * Photographic-looking people (MakeHuman/MPFB, CC0) for the citizens nearest
 * the camera. Everyone further away keeps the instanced figure, so a crowd of
 * hundreds still costs a handful of draw calls.
 */
const MALE = "/models/humans/sam.glb";
const FEMALE = "/models/humans/maya.glb";
const MAX_REAL = 14;
const NEAR = 26;
const ADULT = 0.5;
const STAGE: Record<string, number> = { teenager: 0.88, adult: 1, elder: 0.97 };

useGLTF.preload(MALE);
useGLTF.preload(FEMALE);

function rotationsOnly(clip: AnimationClip): AnimationClip {
  const copy = clip.clone();
  copy.tracks = copy.tracks.filter((t) => !t.name.endsWith(".position") && !t.name.endsWith(".scale"));
  return copy;
}

const WHITE = new Color("#ffffff");

function dress(root: Object3D, look: Looks | undefined) {
  root.traverse((node) => {
    const mesh = node as Mesh;
    if (!mesh.isMesh) return;
    mesh.castShadow = true;
    mesh.frustumCulled = false;
    const swap = (material: Material): Material => {
      const name = material.name.toLowerCase();
      const copy = material.clone() as MeshStandardMaterial;
      if (!look || !copy.color) return copy;
      if (/top|suit/.test(name)) copy.color = new Color(look.clothes).lerp(WHITE, 0.25);
      else if (/short01|ponytail|hair/.test(name)) copy.color = new Color(look.hair).lerp(WHITE, 0.15);
      else if (/\.body$/.test(name)) copy.color = WHITE.clone().lerp(new Color(look.skin), 0.35);
      return copy;
    };
    mesh.material = Array.isArray(mesh.material) ? mesh.material.map(swap) : swap(mesh.material);
  });
}

function RealPerson({ id, female, stage }: { id: number; female: boolean; stage: string }) {
  const male = useGLTF(MALE);
  const woman = useGLTF(FEMALE);
  const source = female ? woman : male;
  const look = useCiv((s) => s.looks.get(id));

  const unit = useMemo(() => {
    source.scene.updateMatrixWorld(true);
    const box = new Box3().setFromObject(source.scene, true);
    const height = box.max.y - box.min.y;
    return height > 0 ? 1 / height : 1;
  }, [source.scene]);

  const model = useMemo(() => {
    const copy = cloneSkinned(source.scene);
    dress(copy, look);
    return copy;
  }, [source.scene, look]);

  const group = useRef<Group>(null);
  const anim = useRef<{ mixer: AnimationMixer; walk?: AnimationAction; idle?: AnimationAction; on?: string } | null>(null);

  useEffect(() => {
    const mixer = new AnimationMixer(model);
    const walkClip = male.animations.find((c) => /walk/i.test(c.name));
    const idleClip = woman.animations.find((c) => /idle/i.test(c.name));
    const walk = walkClip ? mixer.clipAction(rotationsOnly(walkClip)) : undefined;
    const idle = idleClip ? mixer.clipAction(rotationsOnly(idleClip)) : undefined;
    walk?.setLoop(LoopRepeat, Infinity);
    idle?.setLoop(LoopRepeat, Infinity);
    idle?.play();
    if (walk) walk.time = (id * 0.37) % 1;
    anim.current = { mixer, walk, idle, on: "idle" };
    // Only once this body exists does the simple figure step aside.
    realIds.add(id);
    return () => {
      realIds.delete(id);
      mixer.stopAllAction();
      mixer.uncacheRoot(model);
      anim.current = null;
    };
  }, [model, male.animations, woman.animations, id]);

  useFrame((_, dt) => {
    const body = bodies.get(id);
    const g = group.current;
    const a = anim.current;
    if (!body || !g || !a) return;
    const row = useCiv.getState().people.find((p) => p[0] === id);
    const task = row?.[3] ?? "idle";
    const walking = body.speed > 0.08;
    const lying = task === "sleep" && !walking;
    g.position.set(body.x, lying ? 0.06 : 0, body.z);
    g.rotation.set(lying ? -Math.PI / 2 : 0, body.yaw, 0);
    const want = walking ? "walk" : "idle";
    if (a.on !== want) {
      const next = want === "walk" ? a.walk : a.idle;
      const prev = want === "walk" ? a.idle : a.walk;
      if (next) {
        next.reset().play();
        if (prev) prev.crossFadeTo(next, 0.3, false);
      }
      a.on = want;
    }
    if (a.walk && walking) a.walk.timeScale = Math.min(1.8, Math.max(0.6, body.speed / 0.35));
    a.mixer.update(Math.min(dt, 0.1));
  });

  const scale = unit * ADULT * (STAGE[stage] ?? 1) * (look?.height ?? 1);
  const pick = (event: ThreeEvent<MouseEvent>) => {
    event.stopPropagation();
    useCiv.getState().select(id);
  };
  return (
    <group ref={group} onClick={pick}>
      <primitive object={model} scale={scale} />
    </group>
  );
}

/** Chooses who is close enough to deserve a full body, a few times a second. */
export function RealPeople() {
  const camera = useThree((s) => s.camera);
  const [cast, setCast] = useState<{ id: number; female: boolean; stage: string }[]>([]);
  const last = useRef(0);

  useFrame((state) => {
    if (state.clock.elapsedTime - last.current < 0.5) return;
    last.current = state.clock.elapsedTime;
    const { people, playerId, selected } = useCiv.getState();
    const target = camera.position;
    const ranked = people
      .filter((p) => STAGE[p[4]] != null)
      .map((p) => {
        const body = bodies.get(p[0]);
        const x = body?.x ?? p[1];
        const z = body?.z ?? p[2];
        const d = Math.hypot(x - target.x, z - target.z);
        const must = p[0] === playerId || p[0] === selected;
        return { p, d: must ? -1 : d };
      })
      .filter((item) => item.d < NEAR)
      .sort((a, b) => a.d - b.d)
      .slice(0, MAX_REAL);
    const next = ranked.map(({ p }) => ({ id: p[0], female: p[5] === "f", stage: p[4] }));
    setCast((current) => {
      const same = current.length === next.length && current.every((c, i) => c.id === next[i].id && c.stage === next[i].stage);
      return same ? current : next;
    });
  });

  return (
    <Suspense fallback={null}>
      {cast.map((c) => (
        <RealPerson key={c.id} id={c.id} female={c.female} stage={c.stage} />
      ))}
    </Suspense>
  );
}
