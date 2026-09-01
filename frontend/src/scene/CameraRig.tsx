import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { useWorld } from "../store/world";
import { postJson } from "../net/client";

type ControlsHandle = {
  target: { x: number; y: number; z: number };
};

let lastCameraPost = 0;

export function CameraRig({ width, height }: { width: number; height: number }) {
  const controls = useRef<ControlsHandle>(null);
  const follow = useWorld((s) => s.follow);
  const agents = useWorld((s) => s.agents);
  const president = useWorld((s) => s.president);
  const setCamera = useWorld((s) => s.setCamera);

  useFrame(() => {
    const rig = controls.current;
    if (!rig) return;

    if (follow != null) {
      const target =
        follow === "president" ? president : agents.find((agent) => agent.id === follow);
      if (target) {
        rig.target.x += (target.x - rig.target.x) * 0.12;
        rig.target.z += (target.y - rig.target.z) * 0.12;
        rig.target.y = 0.7;
      }
    }

    setCamera(rig.target.x, rig.target.z);

    const now = performance.now();
    if (now - lastCameraPost > 800) {
      lastCameraPost = now;
      void postJson("/api/camera", { x: rig.target.x, y: rig.target.z }).catch(() => {});
    }
  });

  return (
    <OrbitControls
      ref={controls as never}
      makeDefault
      target={[width / 2, 0.8, height / 2]}
      minDistance={2.2}
      maxDistance={90}
      maxPolarAngle={Math.PI / 2.08}
      minPolarAngle={0.18}
      enableDamping
      dampingFactor={0.08}
    />
  );
}
