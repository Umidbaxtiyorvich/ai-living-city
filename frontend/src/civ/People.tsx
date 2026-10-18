import { useMemo, useRef } from "react";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import {
  CapsuleGeometry,
  Color,
  InstancedMesh,
  MathUtils,
  Matrix4,
  Quaternion,
  SphereGeometry,
  BoxGeometry,
  Vector3,
  MeshStandardMaterial,
} from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { useCiv } from "./store";

const MAX = 1200;

/** Smoothed per-person render state, shared with the camera for following. */
export interface Body {
  x: number;
  z: number;
  yaw: number;
  phase: number;
  speed: number;
  seen: number;
}
export const bodies = new Map<number, Body>();
/** People currently drawn as full realistic bodies; the instanced figure hides for them. */
export const realIds = new Set<number>();

const STAGE: Record<string, number> = { baby: 0.32, child: 0.58, teenager: 0.86, adult: 1, elder: 0.96 };
const ADULT = 0.5;
const WORK = new Set(["chop", "quarry", "build", "farm", "forage", "hunt"]);
const SEATED = new Set(["think", "socialize", "eat"]);
const CARRY_COLOUR: Record<string, string> = { food: "#c23b2a", wood: "#7a5230", stone: "#9a968e" };

// Part layout for a 1-unit-tall adult: pivot, rotation axis applied at pivot, then offset.
const HIP = new Vector3(0, 0.47, 0);

function scaleOf(x: number, y: number, z: number) {
  return new Matrix4().makeScale(x, y, z);
}
function offset(x: number, y: number, z: number) {
  return new Matrix4().makeTranslation(x, y, z);
}

/** Thigh hangs 0.235 from the hip; the shin (with its foot) from the knee below it. */
const THIGH = 0.235;
const LEG_AFTER = offset(0, -THIGH / 2, 0);
const SHIN_AFTER = offset(0, -0.12, 0);
const ARM_AFTER = offset(0, -0.17, 0);
const TORSO_AFTER = offset(0, 0.21, 0).multiply(scaleOf(1, 1, 0.68));
const HEAD_AFTER = offset(0, 0.52, 0.01);
const HAIR_MALE = offset(0, 0.555, -0.012).multiply(scaleOf(1.04, 0.82, 1.05));
const HAIR_FEMALE = offset(0, 0.5, -0.03).multiply(scaleOf(1.08, 1.35, 1.12));
const CARRY_AFTER = offset(0, 0.26, 0.17);
const HIDDEN = new Matrix4().makeScale(0, 0, 0);

const colourCache = new Map<string, Color>();
function colour(hex: string): Color {
  let c = colourCache.get(hex);
  if (!c) {
    c = new Color(hex);
    colourCache.set(hex, c);
  }
  return c;
}
const TROUSERS = new Color("#2d2a26");
const SELECT = new Color("#ffe08a");

export function People() {
  const legs = useRef<InstancedMesh>(null);
  const shins = useRef<InstancedMesh>(null);
  const arms = useRef<InstancedMesh>(null);
  const torsos = useRef<InstancedMesh>(null);
  const heads = useRef<InstancedMesh>(null);
  const hair = useRef<InstancedMesh>(null);
  const carried = useRef<InstancedMesh>(null);
  const order = useRef<number[]>([]);

  const geometry = useMemo(
    () => ({
      leg: new CapsuleGeometry(0.062, 0.17, 3, 8),
      shin: (() => {
        // Shin plus a foot pointing forward, so a step shows a heel and toe.
        const shin = new CapsuleGeometry(0.05, 0.17, 3, 8);
        const foot = new BoxGeometry(0.075, 0.04, 0.15);
        foot.translate(0, -0.12, 0.035);
        return mergeGeometries([shin, foot]) ?? shin;
      })(),
      arm: new CapsuleGeometry(0.042, 0.28, 3, 8),
      torso: new CapsuleGeometry(0.125, 0.2, 4, 10),
      head: new SphereGeometry(0.1, 14, 12),
      hair: new SphereGeometry(0.104, 12, 10, 0, Math.PI * 2, 0, Math.PI * 0.62),
      box: new BoxGeometry(0.16, 0.12, 0.12),
    }),
    [],
  );
  const material = useMemo(() => new MeshStandardMaterial({ roughness: 0.75 }), []);
  const skinMaterial = useMemo(() => new MeshStandardMaterial({ roughness: 0.55 }), []);

  // Scratch objects reused every frame — no allocation in the render loop.
  const scratch = useMemo(
    () => ({
      base: new Matrix4(),
      part: new Matrix4(),
      rot: new Matrix4(),
      pivot: new Matrix4(),
      q: new Quaternion(),
      lie: new Quaternion().setFromAxisAngle(new Vector3(1, 0, 0), -Math.PI / 2),
      up: new Vector3(0, 1, 0),
      pos: new Vector3(),
      scl: new Vector3(),
    }),
    [],
  );

  useFrame((state, dt) => {
    const meshes = [legs.current, arms.current, torsos.current, heads.current, hair.current, carried.current, shins.current];
    if (meshes.some((m) => !m)) return;
    const [L, A, T, H, R, C, S] = meshes as InstancedMesh[];
    const { people, looks, selected } = useCiv.getState();
    const t = state.clock.elapsedTime;
    const step = Math.min(dt, 0.1);
    const { base, part, rot, pivot, q, lie, up, pos, scl } = scratch;
    const ids = order.current;
    ids.length = 0;
    let n = 0;

    const put = (mesh: InstancedMesh, index: number, px: number, py: number, pz: number, angle: number, after: Matrix4) => {
      pivot.makeTranslation(px, py, pz);
      rot.makeRotationX(angle);
      part.copy(base).multiply(pivot).multiply(rot).multiply(after);
      mesh.setMatrixAt(index, part);
    };
    // A leg is two bones: the thigh swings from the hip, the shin bends at the knee.
    const leg = (index: number, side: number, thigh: number, knee: number) => {
      put(L, index, side, HIP.y, 0, thigh, LEG_AFTER);
      pivot.makeTranslation(side, HIP.y, 0);
      rot.makeRotationX(thigh);
      part.copy(base).multiply(pivot).multiply(rot);
      pivot.makeTranslation(0, -THIGH, 0);
      rot.makeRotationX(knee);
      part.multiply(pivot).multiply(rot).multiply(SHIN_AFTER);
      S.setMatrixAt(index, part);
    };

    for (const row of people) {
      if (n >= MAX) break;
      const [id, x, y, task, stage, g, carry] = row;
      let body = bodies.get(id);
      if (!body) {
        body = { x, z: y, yaw: 0, phase: Math.random() * 6, speed: 0, seen: t };
        bodies.set(id, body);
      }
      body.seen = t;
      const px = body.x;
      const pz = body.z;
      body.x = MathUtils.damp(body.x, x, 7, step);
      body.z = MathUtils.damp(body.z, y, 7, step);
      const moved = Math.hypot(body.x - px, body.z - pz);
      body.speed = MathUtils.damp(body.speed, step > 0 ? moved / step : 0, 8, step);
      if (Math.hypot(x - body.x, y - body.z) > 0.02) {
        const want = Math.atan2(x - body.x, y - body.z);
        const delta = Math.atan2(Math.sin(want - body.yaw), Math.cos(want - body.yaw));
        body.yaw += delta * Math.min(1, step * 9);
      }
      const walking = body.speed > 0.08;
      body.phase += body.speed * step * 11;

      const look = looks.get(id);
      const female = g === "f";
      const size = ADULT * (STAGE[stage] ?? 1) * (look?.height ?? 1);
      const lying = task === "sleep" && !walking;
      const sitting = !walking && SEATED.has(task);
      const working = !walking && WORK.has(task);
      const baby = stage === "baby";

      q.setFromAxisAngle(up, body.yaw);
      if (lying) q.multiply(lie);
      // The body rises a little over each planted foot, as a real walk does.
      const bob = walking ? Math.abs(Math.cos(body.phase)) * 0.022 * size : 0;
      pos.set(body.x, (lying ? 0.08 : baby ? 0.22 : sitting ? -0.2 * size : 0) + bob, body.z);
      scl.set(size, size, size);
      base.compose(pos, q, scl);

      // Pose. Negative angles swing a limb forward. The knee bends while its
      // leg swings forward (the foot lifts off the ground) and straightens to land.
      const swing = walking ? Math.sin(body.phase) * 0.5 : 0;
      let legL = swing;
      let legR = -swing;
      let kneeL = walking ? 0.12 + Math.max(0, -Math.cos(body.phase)) * 1.0 : 0.04;
      let kneeR = walking ? 0.12 + Math.max(0, Math.cos(body.phase)) * 1.0 : 0.04;
      let armL = -swing * 0.8;
      let armR = swing * 0.8;
      let lean = walking ? 0.06 : 0;
      if (sitting) {
        legL = legR = -1.45;
        kneeL = kneeR = 1.45;
        armL = armR = -0.35;
        lean = -0.05;
      }
      if (working) {
        const beat = Math.sin(t * 6.5 + id);
        if (task === "farm" || task === "forage") {
          lean = 0.55 + beat * 0.08;
          kneeL = kneeR = 0.35;
          legL = legR = -0.2;
          armL = -1.1 + beat * 0.3;
          armR = -1.1 - beat * 0.3;
        } else {
          armL = -2.4 + beat * 1.1;
          armR = -2.3 + beat * 1.1;
          lean = 0.12 + beat * 0.08;
        }
      }
      if (carry && !working) {
        armL = armR = -1.25;
      }

      if (realIds.has(id)) {
        for (const mesh of [L, A, S]) {
          mesh.setMatrixAt(n * 2, HIDDEN);
          mesh.setMatrixAt(n * 2 + 1, HIDDEN);
        }
        for (const mesh of [T, H, R, C]) mesh.setMatrixAt(n, HIDDEN);
        ids.push(id);
        n++;
        continue;
      }

      leg(n * 2, 0.075, legL, kneeL);
      leg(n * 2 + 1, -0.075, legR, kneeR);
      // Arms hang from shoulders that lean with the torso.
      const sy = HIP.y + Math.cos(lean) * 0.38;
      const sz = Math.sin(lean) * 0.38;
      put(A, n * 2, 0.175, sy, sz, armL, ARM_AFTER);
      put(A, n * 2 + 1, -0.175, sy, sz, armR, ARM_AFTER);
      put(T, n, 0, HIP.y, 0, lean, TORSO_AFTER);
      put(H, n, 0, HIP.y, 0, lean, HEAD_AFTER);
      put(R, n, 0, HIP.y, 0, lean, female ? HAIR_FEMALE : HAIR_MALE);
      if (carry) {
        put(C, n, 0, HIP.y, 0, lean, CARRY_AFTER);
        C.setColorAt(n, colour(CARRY_COLOUR[carry] ?? "#aaaaaa"));
      } else {
        C.setMatrixAt(n, HIDDEN);
      }

      const clothes = id === selected ? SELECT : colour(look?.clothes ?? "#3c6e9e");
      const skin = colour(look?.skin ?? "#c68c5a");
      L.setColorAt(n * 2, female ? clothes : TROUSERS);
      L.setColorAt(n * 2 + 1, female ? clothes : TROUSERS);
      S.setColorAt(n * 2, female ? skin : TROUSERS);
      S.setColorAt(n * 2 + 1, female ? skin : TROUSERS);
      A.setColorAt(n * 2, clothes);
      A.setColorAt(n * 2 + 1, clothes);
      T.setColorAt(n, clothes);
      H.setColorAt(n, skin);
      R.setColorAt(n, colour(look?.hair ?? "#2b1d14"));
      ids.push(id);
      n++;
    }

    L.count = n * 2;
    S.count = n * 2;
    A.count = n * 2;
    T.count = n;
    H.count = n;
    R.count = n;
    C.count = n;
    for (const mesh of [L, A, T, H, R, C, S]) {
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }
    // Forget people who have left the stream (died).
    if (Math.floor(t) % 5 === 0) {
      for (const [id, body] of bodies) if (t - body.seen > 4) bodies.delete(id);
    }
  });

  const pick = (event: ThreeEvent<MouseEvent>) => {
    event.stopPropagation();
    const index = event.instanceId;
    if (index == null) return;
    const id = order.current[index];
    if (id != null) useCiv.getState().select(id);
  };

  return (
    <group>
      <instancedMesh ref={legs} args={[geometry.leg, material, MAX * 2]} castShadow frustumCulled={false} />
      <instancedMesh ref={shins} args={[geometry.shin, material, MAX * 2]} castShadow frustumCulled={false} />
      <instancedMesh ref={arms} args={[geometry.arm, material, MAX * 2]} castShadow frustumCulled={false} />
      <instancedMesh ref={torsos} args={[geometry.torso, material, MAX]} castShadow frustumCulled={false} onClick={pick} />
      <instancedMesh ref={heads} args={[geometry.head, skinMaterial, MAX]} castShadow frustumCulled={false} onClick={pick} />
      <instancedMesh ref={hair} args={[geometry.hair, material, MAX]} frustumCulled={false} />
      <instancedMesh ref={carried} args={[geometry.box, material, MAX]} castShadow frustumCulled={false} />
    </group>
  );
}
