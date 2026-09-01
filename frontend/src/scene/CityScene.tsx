import { Canvas } from "@react-three/fiber";
import { ContactShadows, Sky } from "@react-three/drei";
import { useWorld } from "../store/world";
import { Terrain } from "./Terrain";
import { Buildings } from "./Buildings";
import { Citizens } from "./Citizens";
import { CameraRig } from "./CameraRig";
import { WorldProps } from "./WorldProps";
import { StreetProps } from "./StreetProps";
import { Roads } from "./Roads";
import { Vehicles } from "./Vehicles";

export function CityScene() {
  const tiles = useWorld((s) => s.tiles);
  const buildings = useWorld((s) => s.buildings);
  const agents = useWorld((s) => s.agents);
  const president = useWorld((s) => s.president);
  const selection = useWorld((s) => s.selection);
  const follow = useWorld((s) => s.follow);
  const select = useWorld((s) => s.select);
  const night = useWorld((s) => s.dashboard?.time.is_night ?? false);

  if (!tiles) {
    return <div className="loading">Shahar yuklanmoqda…</div>;
  }

  const cx = tiles.width / 2;
  const cz = tiles.height / 2;

  return (
    <Canvas
      shadows
      camera={{
        position: [cx + tiles.width * 0.35, tiles.width * 0.42, cz + tiles.height * 0.55],
        fov: 42,
        near: 0.15,
        far: 400,
      }}
      onPointerMissed={() => select(null)}
    >
      <color attach="background" args={[night ? "#0a1018" : "#7eb8dc"]} />
      <ambientLight intensity={night ? 0.22 : 0.45} />
      <directionalLight
        castShadow
        position={night ? [18, 22, 8] : [45, 55, 28]}
        intensity={night ? 0.55 : 1.85}
        color={night ? "#9bb7ff" : "#fff4e0"}
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-far={180}
        shadow-camera-left={-55}
        shadow-camera-right={55}
        shadow-camera-top={55}
        shadow-camera-bottom={-55}
      />
      <hemisphereLight
        args={[night ? "#1a2744" : "#c8dff5", night ? "#0d1524" : "#3d6a32", night ? 0.35 : 0.62]}
      />
      <Sky
        sunPosition={night ? [0, -1, 0] : [60, 28, 18]}
        turbidity={night ? 2 : 6}
        rayleigh={night ? 0.35 : 1.2}
        mieCoefficient={0.012}
      />
      <fog attach="fog" args={[night ? "#0a1018" : "#a8cce4", 50, 220]} />
      <Terrain tiles={tiles} />
      <Roads tiles={tiles} />
      <Vehicles tiles={tiles} />
      <WorldProps tiles={tiles} />
      <StreetProps tiles={tiles} />
      <Buildings
        buildings={buildings}
        selectedId={selection?.kind === "building" ? selection.id : null}
        onSelect={(id) => select({ kind: "building", id })}
      />
      <Citizens
        agents={agents}
        president={president}
        selectedId={
          selection?.kind === "president" ? -1 : selection?.kind === "agent" ? selection.id : null
        }
        followId={follow}
        onSelect={(id) => select(id === -1 ? { kind: "president" } : { kind: "agent", id })}
      />
      <ContactShadows opacity={0.35} scale={120} blur={1.6} far={8} />
      <CameraRig width={tiles.width} height={tiles.height} />
    </Canvas>
  );
}
