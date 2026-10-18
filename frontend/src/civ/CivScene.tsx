import { useEffect, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Html, OrbitControls, Sky, Stars } from "@react-three/drei";
import { Color, type DirectionalLight, type HemisphereLight, Vector3 } from "three";
import { Ground, Nature } from "./Land";
import { People, bodies } from "./People";
import { Structures } from "./Structures";
import { RealPeople } from "./RealPeople";
import { Wildlife } from "./Wildlife";
import { Ghost } from "./Ghost";

/** Camera heading on the ground, so WASD moves relative to what you see. */
export const view = { azimuth: 0 };
import { useCiv } from "./store";

type Controls = { target: Vector3; object: { position: Vector3 }; update: () => void };

const DAY_SKY = new Color("#8ec5e8");
const DUSK_SKY = new Color("#e8a070");
const NIGHT_SKY = new Color("#1a2a44");

/** Sun, sky and fog follow the simulated hour. */
/** A physically based sky whose sun follows the clock, and stars after dark. */
function Heavens() {
  const hour = useCiv((s) => Math.round((s.time?.hour ?? 12) * 4) / 4);
  const angle = ((hour - 6) / 12) * Math.PI;
  const sun: [number, number, number] = [Math.cos(angle) * 100, Math.sin(angle) * 100, 40];
  const night = hour >= 20.5 || hour < 5;
  return (
    <>
      <Sky distance={450} sunPosition={sun} turbidity={6} rayleigh={night ? 0.2 : 1.4} mieCoefficient={0.006} mieDirectionalG={0.85} />
      {night && <Stars radius={300} depth={60} count={2500} factor={5} fade speed={0.3} />}
    </>
  );
}

function Daylight() {
  const sun = useRef<DirectionalLight>(null);
  const hemi = useRef<HemisphereLight>(null);
  const width = useCiv((s) => s.width);
  const sky = useRef(new Color());

  useFrame(({ scene }) => {
    const hour = useCiv.getState().time?.hour ?? 12;
    // 0 at midnight, 1 at noon.
    const day = Math.max(0, Math.sin(((hour - 6) / 12) * Math.PI));
    const dusk = Math.max(0, 1 - Math.abs(hour - 18.5) / 1.6) + Math.max(0, 1 - Math.abs(hour - 6) / 1.4);
    sky.current.copy(NIGHT_SKY).lerp(DAY_SKY, Math.min(1, day * 1.4)).lerp(DUSK_SKY, Math.min(0.55, dusk * 0.5));
    scene.background = sky.current;
    if (scene.fog) (scene.fog as unknown as { color: Color }).color.copy(sky.current);
    if (sun.current) {
      const angle = ((hour - 6) / 12) * Math.PI;
      const target = followTarget();
      sun.current.position.set(target.x + Math.cos(angle) * 40, 10 + Math.max(0, Math.sin(angle)) * 45, target.z + 20);
      sun.current.target.position.set(target.x, 0, target.z);
      sun.current.target.updateMatrixWorld();
      sun.current.intensity = 0.45 + day * 1.7;
      // Warm sunlight by day, cool moonlight by night.
      sun.current.color.setHSL(day > 0.05 ? 0.1 : 0.6, day > 0.05 ? 0.5 : 0.35, 0.72 + day * 0.2);
    }
    if (hemi.current) hemi.current.intensity = 0.5 + day * 0.4;
  });

  return (
    <>
      <hemisphereLight ref={hemi} args={["#cfe6ff", "#4a6a35", 0.6]} />
      <directionalLight
        ref={sun}
        castShadow
        intensity={1.8}
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
        shadow-camera-left={-28}
        shadow-camera-right={28}
        shadow-camera-top={28}
        shadow-camera-bottom={-28}
        shadow-camera-far={140}
        shadow-bias={-0.0006}
      />
      <fog attach="fog" args={["#8ec5e8", Math.max(40, width * 0.6), Math.max(120, width * 1.6)]} />
    </>
  );
}

let lastTarget = new Vector3();
function followTarget(): Vector3 {
  return lastTarget;
}

function Camera() {
  const controls = useRef<Controls | null>(null);
  const focus = useCiv((s) => s.focus);
  const width = useCiv((s) => s.width);
  const booted = useRef(false);

  useEffect(() => {
    const rig = controls.current;
    if (!rig || !focus) return;
    const offset = rig.object.position.clone().sub(rig.target);
    rig.target.set(focus.x, 0, focus.z);
    rig.object.position.copy(rig.target).add(offset);
    rig.update();
  }, [focus]);

  useFrame(() => {
    const rig = controls.current;
    if (!rig) return;
    const state = useCiv.getState();
    if (!booted.current && state.settlements.length) {
      booted.current = true;
      const home = state.settlements[0];
      rig.target.set(home.x, 0, home.y);
      rig.object.position.set(home.x + 9, 11, home.y + 13);
      rig.update();
    }
    if (state.follow != null) {
      const body = bodies.get(state.follow);
      if (body) {
        const dx = body.x - rig.target.x;
        const dz = body.z - rig.target.z;
        rig.target.x += dx * 0.1;
        rig.target.z += dz * 0.1;
        rig.object.position.x += dx * 0.1;
        rig.object.position.z += dz * 0.1;
      }
    }
    lastTarget = rig.target;
    view.azimuth = Math.atan2(rig.object.position.x - rig.target.x, rig.object.position.z - rig.target.z);
  });

  return (
    <OrbitControls
      ref={controls as never}
      makeDefault
      target={[width / 2, 0, width / 2]}
      minDistance={2.5}
      maxDistance={140}
      maxPolarAngle={Math.PI / 2.15}
      enableDamping
      dampingFactor={0.1}
    />
  );
}

function PersonTag() {
  const selected = useCiv((s) => s.selected);
  const looks = useCiv((s) => (s.selected != null && s.selected > 0 ? s.looks.get(s.selected) : undefined));
  const row = useCiv((s) => (s.selected != null && s.selected > 0 ? s.people.find((p) => p[0] === s.selected) : undefined));
  const labels = useCiv((s) => s.labels);
  const group = useRef<{ position: Vector3 } | null>(null);
  useFrame(() => {
    if (!group.current || selected == null) return;
    const body = bodies.get(selected);
    if (body) group.current.position.set(body.x, 0.9, body.z);
  });
  if (selected == null || selected <= 0 || !row) return null;
  return (
    <group ref={group as never}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.88, 0]}>
        <ringGeometry args={[0.2, 0.26, 24]} />
        <meshBasicMaterial color="#ffe08a" />
      </mesh>
      <Html center distanceFactor={9} zIndexRange={[10, 0]}>
        <div className="civ-tag">
          <strong>{looks?.name ?? `#${selected}`}</strong>
          <span>{labels[row[3]] ?? row[3]}</span>
        </div>
      </Html>
    </group>
  );
}

function SettlementNames() {
  const settlements = useCiv((s) => s.settlements);
  return (
    <>
      {settlements.map((s) => (
        <Html key={s.id} position={[s.x, 2.6, s.y]} center distanceFactor={26} zIndexRange={[5, 0]}>
          <div className="civ-place">
            <strong>{s.name}</strong>
            <span>
              {s.rank} · {s.population}
            </span>
          </div>
        </Html>
      ))}
    </>
  );
}

export function CivScene() {
  const width = useCiv((s) => s.width);
  const select = useCiv((s) => s.select);
  if (!width) return <div className="loading">Dunyo yaratilmoqda…</div>;
  return (
    <Canvas
      shadows
      dpr={[1, 1.5]}
      camera={{ position: [width / 2 + 10, 14, width / 2 + 14], fov: 45, near: 0.1, far: 600 }}
      onPointerMissed={() => select(null)}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      onCreated={(three) => {
        // Dev-only handle for profiling the renderer from the console.
        if (import.meta.env.DEV) (window as unknown as { __civ3: unknown }).__civ3 = three;
      }}
    >
      <Heavens />
      <Daylight />
      <Ground />
      <Nature />
      <Structures />
      <People />
      <RealPeople />
      <Wildlife />
      <Ghost />
      <PersonTag />
      <SettlementNames />
      <Camera />
    </Canvas>
  );
}
