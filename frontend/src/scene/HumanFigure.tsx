import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { Group, MathUtils } from "three";
import { ACTIVITY_LINE, lookFromSeed } from "./look";

const STAGE_SCALE: Record<string, number> = {
  baby: 0.38,
  toddler: 0.48,
  child: 0.62,
  teenager: 0.84,
  adult: 1,
  senior: 0.94,
};

export function HumanFigure({
  id,
  x,
  z,
  name,
  gender,
  age,
  stage,
  activity,
  profession,
  seed,
  selected,
  president = false,
  showLabel,
  onSelect,
}: {
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
  onSelect: (id: number) => void;
}) {
  const look = useMemo(
    () => lookFromSeed(seed || `id-${id}`, gender, age, profession, president),
    [seed, id, gender, age, profession, president],
  );
  const root = useRef<Group>(null);
  const leftLeg = useRef<Group>(null);
  const rightLeg = useRef<Group>(null);
  const leftArm = useRef<Group>(null);
  const rightArm = useRef<Group>(null);
  const smoothed = useRef({ x, z, yaw: 0 });
  const scale = STAGE_SCALE[stage] ?? 1;
  const walking = activity === "commuting" || activity === "going_home" || activity === "leisure" || activity === "shopping" || activity === "seeking_job" || activity === "working" || activity === "city" || activity === "inspections";
  const sleeping = activity === "sleeping";
  const line = ACTIVITY_LINE[activity] ?? activity;

  useFrame((state, dt) => {
    const hold = smoothed.current;
    const dx = x - hold.x;
    const dz = z - hold.z;
    hold.x = MathUtils.damp(hold.x, x, 8, dt);
    hold.z = MathUtils.damp(hold.z, z, 8, dt);
    if (Math.hypot(dx, dz) > 0.004) {
      hold.yaw = Math.atan2(dx, dz);
    }
    const group = root.current;
    if (!group) return;
    group.position.set(hold.x, sleeping ? 0.18 * scale : 0, hold.z);
    group.rotation.x = sleeping ? -Math.PI / 2.2 : 0;
    group.rotation.y = hold.yaw;

    const t = state.clock.elapsedTime;
    const swing = walking && !sleeping ? Math.sin(t * 9 + id) * 0.7 : 0;
    if (leftLeg.current) leftLeg.current.rotation.x = swing;
    if (rightLeg.current) rightLeg.current.rotation.x = -swing;
    if (leftArm.current) leftArm.current.rotation.x = -swing * 0.75;
    if (rightArm.current) rightArm.current.rotation.x = swing * 0.75;
  });

  const s = 0.42 * scale * look.body;
  const skin = look.skin;
  const cloth = selected ? "#FFE08A" : look.clothes;

  return (
    <group
      ref={root}
      scale={s}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(id);
      }}
    >
      {/* hips / legs */}
      <group ref={leftLeg} position={[0.09, 0.42, 0]}>
        <mesh position={[0, -0.22, 0]} castShadow>
          <capsuleGeometry args={[0.07, 0.28, 4, 6]} />
          <meshStandardMaterial color={look.female ? look.clothes2 : "#2A2420"} roughness={0.8} />
        </mesh>
        <mesh position={[0, -0.42, 0.02]} castShadow>
          <boxGeometry args={[0.1, 0.05, 0.16]} />
          <meshStandardMaterial color={look.shoes} />
        </mesh>
      </group>
      <group ref={rightLeg} position={[-0.09, 0.42, 0]}>
        <mesh position={[0, -0.22, 0]} castShadow>
          <capsuleGeometry args={[0.07, 0.28, 4, 6]} />
          <meshStandardMaterial color={look.female ? look.clothes2 : "#2A2420"} roughness={0.8} />
        </mesh>
        <mesh position={[0, -0.42, 0.02]} castShadow>
          <boxGeometry args={[0.1, 0.05, 0.16]} />
          <meshStandardMaterial color={look.shoes} />
        </mesh>
      </group>

      {/* torso / chapan or atlas dress */}
      <mesh position={[0, 0.72, 0]} castShadow>
        <capsuleGeometry args={[look.female ? 0.2 : 0.18, look.female ? 0.42 : 0.38, 6, 10]} />
        <meshStandardMaterial color={cloth} roughness={0.55} />
      </mesh>
      {look.female && (
        <mesh position={[0, 0.48, 0]} castShadow>
          <coneGeometry args={[0.28, 0.5, 8]} />
          <meshStandardMaterial color={look.clothes2} roughness={0.6} />
        </mesh>
      )}
      <mesh position={[0, 0.86, 0.12]}>
        <boxGeometry args={[0.28, 0.08, 0.04]} />
        <meshStandardMaterial color={look.clothes2} />
      </mesh>

      {/* arms */}
      <group ref={leftArm} position={[0.24, 0.92, 0]}>
        <mesh position={[0.02, -0.18, 0]} rotation={[0, 0, 0.25]} castShadow>
          <capsuleGeometry args={[0.055, 0.32, 4, 6]} />
          <meshStandardMaterial color={skin} />
        </mesh>
      </group>
      <group ref={rightArm} position={[-0.24, 0.92, 0]}>
        <mesh position={[-0.02, -0.18, 0]} rotation={[0, 0, -0.25]} castShadow>
          <capsuleGeometry args={[0.055, 0.32, 4, 6]} />
          <meshStandardMaterial color={skin} />
        </mesh>
      </group>

      {/* head + face */}
      <mesh position={[0, 1.22, 0]} castShadow>
        <sphereGeometry args={[0.16, 14, 14]} />
        <meshStandardMaterial color={skin} roughness={0.45} />
      </mesh>
      <mesh position={[0.055, 1.24, 0.13]}>
        <sphereGeometry args={[0.028, 8, 8]} />
        <meshStandardMaterial color="#FAFAFA" />
      </mesh>
      <mesh position={[-0.055, 1.24, 0.13]}>
        <sphereGeometry args={[0.028, 8, 8]} />
        <meshStandardMaterial color="#FAFAFA" />
      </mesh>
      <mesh position={[0.055, 1.24, 0.152]}>
        <sphereGeometry args={[0.016, 8, 8]} />
        <meshStandardMaterial color={look.eyes} />
      </mesh>
      <mesh position={[-0.055, 1.24, 0.152]}>
        <sphereGeometry args={[0.016, 8, 8]} />
        <meshStandardMaterial color={look.eyes} />
      </mesh>
      <mesh position={[0, 1.2, 0.155]}>
        <sphereGeometry args={[0.03, 8, 8]} />
        <meshStandardMaterial color={skin} />
      </mesh>
      <mesh position={[0, 1.155, 0.145]}>
        <boxGeometry args={[0.06, 0.012, 0.02]} />
        <meshStandardMaterial color="#7A3E36" />
      </mesh>
      {look.beard && (
        <mesh position={[0, 1.14, 0.1]}>
          <sphereGeometry args={[0.09, 8, 8]} />
          <meshStandardMaterial color={look.hair} />
        </mesh>
      )}

      <Hair lookHair={look.hair} style={look.hairStyle} female={look.female} />
      {look.doppi && (
        <group position={[0, 1.36, 0]}>
          <mesh>
            <cylinderGeometry args={[0.13, 0.15, 0.1, 10]} />
            <meshStandardMaterial color={look.doppi} roughness={0.55} />
          </mesh>
          <mesh position={[0, 0.06, 0]}>
            <torusGeometry args={[0.13, 0.018, 6, 12]} />
            <meshStandardMaterial color={look.clothes2} />
          </mesh>
        </group>
      )}

      {president && (
        <mesh position={[0, 0.95, 0.14]}>
          <boxGeometry args={[0.12, 0.16, 0.02]} />
          <meshStandardMaterial color="#C9A227" metalness={0.5} roughness={0.3} />
        </mesh>
      )}

      {showLabel && (
        <Html center distanceFactor={10} position={[0, 1.7, 0]} occlude={false}>
          <div className="agent-label">
            <strong>{name}</strong>
            <span>{line}</span>
          </div>
        </Html>
      )}
    </group>
  );
}

function Hair({
  lookHair,
  style,
  female,
}: {
  lookHair: string;
  style: string;
  female: boolean;
}) {
  if (style === "buzz") {
    return (
      <mesh position={[0, 1.32, 0]}>
        <sphereGeometry args={[0.162, 10, 10]} />
        <meshStandardMaterial color={lookHair} />
      </mesh>
    );
  }
  if (style === "braid" || style === "long") {
    return (
      <group>
        <mesh position={[0, 1.3, -0.02]}>
          <sphereGeometry args={[0.17, 12, 12]} />
          <meshStandardMaterial color={lookHair} />
        </mesh>
        <mesh position={[0.08, 0.95, -0.08]} rotation={[0.4, 0, 0.2]}>
          <capsuleGeometry args={[0.045, 0.45, 4, 6]} />
          <meshStandardMaterial color={lookHair} />
        </mesh>
        <mesh position={[-0.08, 0.95, -0.08]} rotation={[0.4, 0, -0.2]}>
          <capsuleGeometry args={[0.045, 0.45, 4, 6]} />
          <meshStandardMaterial color={lookHair} />
        </mesh>
      </group>
    );
  }
  if (style === "bun") {
    return (
      <group>
        <mesh position={[0, 1.3, -0.02]}>
          <sphereGeometry args={[0.17, 12, 12]} />
          <meshStandardMaterial color={lookHair} />
        </mesh>
        <mesh position={[0, 1.4, -0.08]}>
          <sphereGeometry args={[0.08, 10, 10]} />
          <meshStandardMaterial color={lookHair} />
        </mesh>
      </group>
    );
  }
  return (
    <mesh position={[0, female ? 1.31 : 1.33, -0.01]}>
      <sphereGeometry args={[0.168, 12, 12]} />
      <meshStandardMaterial color={lookHair} />
    </mesh>
  );
}
