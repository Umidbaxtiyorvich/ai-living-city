import { Component, useEffect, useMemo, useRef, type ReactNode } from "react";
import { useFrame } from "@react-three/fiber";
import { Html, useGLTF } from "@react-three/drei";
import {
  AnimationAction,
  AnimationClip,
  AnimationMixer,
  Box3,
  Color,
  Group,
  LoopRepeat,
  MathUtils,
  Mesh,
  MeshStandardMaterial,
  type Material,
  type Object3D,
} from "three";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";
import { ACTIVITY_LINE, lookFromSeed } from "./look";
import { assetUrl, clipFor, type ClipRole, type HumanModelEntry } from "./humanModels";

/** World-units height of an adult; matches the procedural figures and the map scale. */
const ADULT_HEIGHT = 0.62;

const STAGE_SCALE: Record<string, number> = {
  baby: 0.38,
  toddler: 0.48,
  child: 0.62,
  teenager: 0.86,
  adult: 1,
  senior: 0.95,
};

/** Activities where a citizen at rest is seated rather than standing. */
const SEATED = new Set(["working", "studying", "at_school", "eating", "office", "meetings", "reports"]);

/** Tiles per second (in sim-rendered motion) above which the walk turns into a run. */
const RUN_SPEED = 1.6;
const WALK_SPEED = 0.04;

/** Clips borrowed from another file keep only rotations, so foreign rest heights cannot float the body. */
function rotationsOnly(clip: AnimationClip): AnimationClip {
  const copy = clip.clone();
  copy.tracks = copy.tracks.filter((track) => !track.name.endsWith(".position") && !track.name.endsWith(".scale"));
  return copy;
}

function recolour(root: Object3D, entry: HumanModelEntry, clothes: string, skin: string) {
  const tint = (entry.tint ?? []).map((s) => s.toLowerCase());
  const skinKeys = (entry.skin ?? []).map((s) => s.toLowerCase());
  root.traverse((node) => {
    const mesh = node as Mesh;
    if (!mesh.isMesh) return;
    mesh.castShadow = true;
    mesh.frustumCulled = false;
    const swap = (material: Material): Material => {
      const name = material.name.toLowerCase();
      const isCloth = tint.some((key) => name.includes(key));
      const isSkin = skinKeys.some((key) => name.includes(key));
      if (!isCloth && !isSkin) return material;
      const copy = material.clone() as MeshStandardMaterial;
      if (copy.color) copy.color = new Color(isSkin ? skin : clothes);
      return copy;
    };
    mesh.material = Array.isArray(mesh.material) ? mesh.material.map(swap) : swap(mesh.material);
  });
}

export interface RiggedHumanProps {
  entry: HumanModelEntry;
  id: number;
  x: number;
  z: number;
  name: string;
  gender: string;
  age: number;
  stage: string;
  activity: string;
  profession: string | null;
  seed: string;
  selected: boolean;
  president?: boolean;
  showLabel: boolean;
  thought?: string;
  onSelect: (id: number) => void;
}

export function RiggedHuman(props: RiggedHumanProps) {
  const { entry, id, x, z, name, gender, age, stage, activity, profession, seed, selected, president = false, showLabel, thought, onSelect } = props;
  const gltf = useGLTF(assetUrl(entry.url));
  const borrowed = useGLTF(assetUrl(entry.clipSource ?? entry.url));

  const look = useMemo(
    () => lookFromSeed(seed || `id-${id}`, gender, age, profession, president),
    [seed, id, gender, age, profession, president],
  );

  // Height normalisation is per asset, not per citizen.
  const unit = useMemo(() => {
    const box = new Box3().setFromObject(gltf.scene);
    const height = box.max.y - box.min.y;
    return height > 0 ? ADULT_HEIGHT / height : 1;
  }, [gltf.scene]);

  const model = useMemo(() => {
    const copy = cloneSkinned(gltf.scene);
    recolour(copy, entry, look.clothes, look.skin);
    return copy;
  }, [gltf.scene, entry, look]);

  const clips = useMemo(() => {
    const own = gltf.animations;
    const extra = entry.clipSource ? borrowed.animations.map(rotationsOnly) : [];
    return [...own, ...extra];
  }, [gltf.animations, borrowed.animations, entry.clipSource]);

  const root = useRef<Group>(null);
  const smoothed = useRef({ x, z, yaw: 0, speed: 0 });
  const current = useRef<ClipRole | null>(null);
  // The mixer lives inside an effect so its lifetime matches the mount: React's
  // dev double-mount would otherwise uncache bindings that memoised actions
  // still point at.
  const anim = useRef<{ mixer: AnimationMixer; actions: Partial<Record<ClipRole, AnimationAction>> } | null>(null);

  useEffect(() => {
    const mixer = new AnimationMixer(model);
    const names = clips.map((clip) => clip.name);
    const actions: Partial<Record<ClipRole, AnimationAction>> = {};
    for (const role of ["idle", "walk", "run", "sit", "work"] as ClipRole[]) {
      const clipName = clipFor(role, names, entry);
      const clip = clips.find((item) => item.name === clipName);
      if (clip) {
        const action = mixer.clipAction(clip);
        action.setLoop(LoopRepeat, Infinity);
        actions[role] = action;
      }
    }
    anim.current = { mixer, actions };
    current.current = null;
    return () => {
      mixer.stopAllAction();
      mixer.uncacheRoot(model);
      anim.current = null;
    };
  }, [model, clips, entry]);
  // Offset the cycle per citizen so a crowd never marches in lockstep.
  const phase = useMemo(() => ((id * 0.618) % 1) * 2, [id]);
  const scale = (STAGE_SCALE[stage] ?? 1) * look.body * unit;
  const sleeping = activity === "sleeping";

  useFrame((_, dt) => {
    const hold = smoothed.current;
    const px = hold.x;
    const pz = hold.z;
    hold.x = MathUtils.damp(hold.x, x, 8, dt);
    hold.z = MathUtils.damp(hold.z, z, 8, dt);
    const moved = Math.hypot(hold.x - px, hold.z - pz);
    const instant = dt > 0 ? moved / dt : 0;
    hold.speed = MathUtils.damp(hold.speed, instant, 6, dt);
    if (Math.hypot(x - hold.x, z - hold.z) > 0.004) {
      const targetYaw = Math.atan2(x - hold.x, z - hold.z) + (entry.yaw ?? 0);
      // Shortest-arc turn so citizens do not spin the long way round.
      const delta = Math.atan2(Math.sin(targetYaw - hold.yaw), Math.cos(targetYaw - hold.yaw));
      hold.yaw += delta * Math.min(1, dt * 10);
    }

    const group = root.current;
    if (group) {
      group.position.set(hold.x, sleeping ? 0.08 * scale : 0, hold.z);
      group.rotation.set(sleeping ? -Math.PI / 2 : 0, hold.yaw, 0);
    }

    const state = anim.current;
    if (!state) return;
    const { mixer, actions } = state;
    let role: ClipRole = "idle";
    if (!sleeping) {
      if (hold.speed > RUN_SPEED && actions.run) role = "run";
      else if (hold.speed > WALK_SPEED && actions.walk) role = "walk";
      else if (SEATED.has(activity) && actions.sit) role = "sit";
      else if (SEATED.has(activity) && actions.work) role = "work";
    }
    if (!actions[role]) role = actions.idle ? "idle" : (Object.keys(actions)[0] as ClipRole);

    if (role && current.current !== role) {
      const next = actions[role];
      const previous = current.current ? actions[current.current] : undefined;
      if (next) {
        next.reset();
        next.time = phase;
        next.play();
        if (previous && previous !== next) previous.crossFadeTo(next, 0.25, false);
      }
      current.current = role;
    }
    const active = current.current ? actions[current.current] : undefined;
    if (active && (current.current === "walk" || current.current === "run")) {
      active.timeScale = MathUtils.clamp(hold.speed / (current.current === "run" ? 2.2 : 0.7), 0.6, 1.6);
    } else if (active) {
      active.timeScale = 1;
    }
    mixer.update(dt);
  });

  const line = ACTIVITY_LINE[activity] ?? activity;

  return (
    <group
      ref={root}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(id);
      }}
    >
      <primitive object={model} scale={scale} />
      {selected && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
          <ringGeometry args={[0.16, 0.2, 24]} />
          <meshBasicMaterial color="#FFE08A" transparent opacity={0.9} />
        </mesh>
      )}
      {president && (
        <mesh position={[0, ADULT_HEIGHT * 0.95, 0]}>
          <torusGeometry args={[0.09, 0.012, 6, 18]} />
          <meshStandardMaterial color="#C9A227" metalness={0.6} roughness={0.3} emissive="#5a4510" />
        </mesh>
      )}
      {showLabel && (
        <Html center distanceFactor={10} position={[0, ADULT_HEIGHT * scale / unit + 0.25, 0]} occlude={false}>
          <div className="agent-label">
            <strong>{name}</strong>
            <span>{line}</span>
            {thought && selected ? <em>💭 {thought}</em> : null}
          </div>
        </Html>
      )}
    </group>
  );
}

/** Falls back to the procedural figure if a model file is missing or broken. */
export class ModelBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.warn("Human model failed to load; using the procedural figure.", error);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
