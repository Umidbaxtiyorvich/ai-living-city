import { Suspense, useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import { type AnimationAction, AnimationMixer, Box3, Group, LoopRepeat, MathUtils, Mesh, type Object3D } from "three";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";
import { useCiv } from "./store";

/** World units are ~3.5 m (a person is 0.5 tall), so sizes below are in those units. */
const MODELS: Record<string, { url: string; size: number; skinned: boolean; walk?: RegExp; rest?: RegExp }> = {
  horse: { url: "/models/animals/Horse.glb", size: 0.5, skinned: false },
  fox: { url: "/models/animals/Fox.glb", size: 0.2, skinned: true, walk: /walk/i, rest: /survey/i },
  stork: { url: "/models/animals/Stork.glb", size: 0.42, skinned: false },
  flamingo: { url: "/models/animals/Flamingo.glb", size: 0.42, skinned: false },
  parrot: { url: "/models/animals/Parrot.glb", size: 0.3, skinned: false },
};
Object.values(MODELS).forEach((m) => useGLTF.preload(m.url));

function useCreature(kind: string) {
  const spec = MODELS[kind];
  const gltf = useGLTF(spec.url);
  // Measured from the actual vertices (morph targets would inflate a loose box),
  // then lifted so the feet stand on the ground.
  const { scale, lift } = useMemo(() => {
    gltf.scene.updateMatrixWorld(true);
    const box = new Box3().setFromObject(gltf.scene, true);
    const longest = Math.max(box.max.x - box.min.x, box.max.y - box.min.y, box.max.z - box.min.z);
    const k = longest > 0 ? spec.size / longest : 1;
    return { scale: k, lift: -box.min.y * k };
  }, [gltf.scene, spec.size]);
  const model = useMemo(() => {
    const copy: Object3D = spec.skinned ? cloneSkinned(gltf.scene) : gltf.scene.clone(true);
    copy.traverse((node) => {
      const mesh = node as Mesh;
      if (mesh.isMesh) {
        mesh.castShadow = true;
        mesh.frustumCulled = false;
      }
    });
    return copy;
  }, [gltf.scene, spec.skinned]);
  return { gltf, model, scale, lift, spec };
}

function Animal({ id, kind }: { id: number; kind: string }) {
  const { gltf, model, scale, lift, spec } = useCreature(kind);
  const group = useRef<Group>(null);
  const state = useRef({ x: 0, z: 0, yaw: 0, init: false });
  // Mixer and actions live for exactly one mount (React may mount twice in dev).
  const anim = useRef<{ mixer: AnimationMixer; walk?: AnimationAction; rest?: AnimationAction } | null>(null);
  useEffect(() => {
    const mixer = new AnimationMixer(model);
    const clips = gltf.animations;
    const walkClip = clips.find((c) => (spec.walk ? spec.walk.test(c.name) : true));
    const restClip = clips.find((c) => (spec.rest ? spec.rest.test(c.name) : false));
    const walk = walkClip ? mixer.clipAction(walkClip).setLoop(LoopRepeat, Infinity) : undefined;
    const rest = restClip ? mixer.clipAction(restClip).setLoop(LoopRepeat, Infinity) : undefined;
    walk?.play();
    rest?.play();
    anim.current = { mixer, walk, rest };
    return () => {
      mixer.stopAllAction();
      mixer.uncacheRoot(model);
      anim.current = null;
    };
  }, [gltf.animations, model, spec]);

  useFrame((_, dt) => {
    const row = useCiv.getState().animals.find((a) => a[0] === id);
    const g = group.current;
    if (!row || !g) return;
    const s = state.current;
    if (!s.init) {
      s.x = row[2];
      s.z = row[3];
      s.init = true;
    }
    const px = s.x;
    const pz = s.z;
    s.x = MathUtils.damp(s.x, row[2], 4, dt);
    s.z = MathUtils.damp(s.z, row[3], 4, dt);
    if (Math.hypot(s.x - px, s.z - pz) > 0.0005) {
      const want = Math.atan2(s.x - px, s.z - pz);
      s.yaw += Math.atan2(Math.sin(want - s.yaw), Math.cos(want - s.yaw)) * Math.min(1, dt * 5);
    }
    g.position.set(s.x, 0, s.z);
    g.rotation.y = s.yaw;
    const a = anim.current;
    if (!a) return;
    const moving = row[4] === 1;
    if (a.walk) a.walk.weight = moving ? 1 : a.rest ? 0 : 0.05;
    if (a.rest) a.rest.weight = moving ? 0 : 1;
    // A grazing horse barely moves its legs; a walking one gallops slowly.
    a.mixer.update(Math.min(dt, 0.1) * (moving ? (kind === "horse" ? 0.55 : 1) : 0.25));
  });

  return (
    <group ref={group}>
      <primitive object={model} scale={scale} position={[0, lift, 0]} />
    </group>
  );
}

function Bird({ kind, cx, cz, radius, height, phase, speed }: { kind: string; cx: number; cz: number; radius: number; height: number; phase: number; speed: number }) {
  const { gltf, model, scale } = useCreature(kind);
  const group = useRef<Group>(null);
  const mixerRef = useRef<AnimationMixer | null>(null);
  useEffect(() => {
    const mixer = new AnimationMixer(model);
    const clip = gltf.animations[0];
    if (clip) {
      const action = mixer.clipAction(clip);
      action.time = phase;
      action.play();
    }
    mixerRef.current = mixer;
    return () => {
      mixer.stopAllAction();
      mixer.uncacheRoot(model);
      mixerRef.current = null;
    };
  }, [gltf.animations, model, phase]);
  useFrame((st, dt) => {
    const g = group.current;
    if (!g) return;
    const night = useCiv.getState().time?.night ?? false;
    g.visible = !night;
    const t = st.clock.elapsedTime * speed + phase;
    const x = cx + Math.cos(t) * radius;
    const z = cz + Math.sin(t) * radius * 0.8;
    g.position.set(x, height + Math.sin(t * 3) * 0.3, z);
    // Fly along the tangent of the loop.
    g.rotation.y = Math.atan2(-Math.sin(t), Math.cos(t) * 0.8);
    mixerRef.current?.update(Math.min(dt, 0.1));
  });
  return (
    <group ref={group}>
      <primitive object={model} scale={scale} />
    </group>
  );
}

function hash(n: number): number {
  const x = Math.sin(n * 127.1) * 43758.5453;
  return x - Math.floor(x);
}

export function Wildlife() {
  const animals = useCiv((s) => s.animals.map((a) => `${a[0]}:${a[1]}`).join(","));
  const width = useCiv((s) => s.width);
  const settlements = useCiv((s) => s.settlements.map((t) => `${t.x},${t.y}`).join(";"));
  const list = useMemo(
    () => (animals ? animals.split(",").map((item) => {
      const [id, kind] = item.split(":");
      return { id: Number(id), kind };
    }) : []),
    [animals],
  );
  const flocks = useMemo(() => {
    const centres = settlements ? settlements.split(";").map((p) => p.split(",").map(Number)) : [[width / 2, width / 2]];
    const out: { key: string; kind: string; cx: number; cz: number; radius: number; height: number; phase: number; speed: number }[] = [];
    const kinds = ["stork", "flamingo", "parrot"];
    centres.slice(0, 3).forEach(([x, z], c) => {
      for (let b = 0; b < 4; b++) {
        const n = c * 10 + b;
        out.push({
          key: `b${n}`,
          kind: kinds[(c + (b % 2)) % kinds.length],
          cx: x + (hash(n) - 0.5) * 16,
          cz: z + (hash(n + 3) - 0.5) * 16,
          radius: 6 + hash(n + 5) * 10,
          height: 3.5 + hash(n + 7) * 3,
          phase: hash(n + 9) * 6.28,
          speed: 0.12 + hash(n + 11) * 0.1,
        });
      }
    });
    return out;
  }, [settlements, width]);

  return (
    <Suspense fallback={null}>
      {list.map((a) => (
        <Animal key={a.id} id={a.id} kind={a.kind} />
      ))}
      {flocks.map(({ key, ...f }) => (
        <Bird key={key} {...f} />
      ))}
    </Suspense>
  );
}
