import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { Mesh } from "three";
import { hover } from "./Land";
import { useCiv } from "./store";

/** A translucent footprint that follows the pointer while a building is being placed. */
export function Ghost() {
  const mesh = useRef<Mesh>(null);
  const placing = useCiv((s) => s.placing);
  const blueprint = useCiv((s) => s.blueprints.find((b) => b.kind === s.placing));
  useFrame(() => {
    const m = mesh.current;
    if (!m || !blueprint) return;
    m.visible = hover.active;
    const ox = Math.round(hover.x - (blueprint.w - 1) / 2);
    const oy = Math.round(hover.y - (blueprint.h - 1) / 2);
    m.position.set(ox + (blueprint.w - 1) / 2, 0.3, oy + (blueprint.h - 1) / 2);
  });
  if (!placing || !blueprint) return null;
  return (
    <mesh ref={mesh} scale={[blueprint.w * 0.95, 0.6, blueprint.h * 0.95]}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color="#7fe08a" transparent opacity={0.45} />
    </mesh>
  );
}
