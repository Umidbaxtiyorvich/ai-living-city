import { Suspense, useMemo } from "react";
import { HumanFigure } from "./HumanFigure";
import { ModelBoundary, RiggedHuman } from "./RiggedHuman";
import { pickModel, useHumanManifest, type HumanModelEntry } from "./humanModels";
import { useWorld } from "../store/world";
import type { AgentView, PresidentView } from "../types";

const MAX_VISIBLE = 72;
const VIEW_RADIUS = 65;
/**
 * Citizens nearest the camera get a skinned, animated model; the rest keep the
 * cheap procedural figure. Skinned meshes cost a mixer and a skeleton each, so
 * this bound is what keeps a large city at a steady frame rate.
 */
const MAX_RIGGED = 28;

interface FigureProps {
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

function Person({ entry, ...props }: FigureProps & { entry: HumanModelEntry | null }) {
  const procedural = <HumanFigure {...props} />;
  if (!entry) return procedural;
  return (
    <ModelBoundary fallback={procedural}>
      <Suspense fallback={procedural}>
        <RiggedHuman entry={entry} {...props} />
      </Suspense>
    </ModelBoundary>
  );
}

export function Citizens({
  agents,
  president,
  selectedId,
  followId,
  onSelect,
}: {
  agents: AgentView[];
  president: PresidentView | null;
  selectedId: number | null;
  followId: number | "president" | null;
  onSelect: (id: number) => void;
}) {
  const cameraX = useWorld((s) => s.cameraX);
  const cameraZ = useWorld((s) => s.cameraZ);
  const models = useHumanManifest();

  const visible = useMemo(() => {
    const must = new Set<number>();
    if (selectedId != null && selectedId >= 0) must.add(selectedId);
    if (typeof followId === "number") must.add(followId);

    const ranked = agents
      .map((agent) => ({
        agent,
        dist: (agent.x - cameraX) ** 2 + (agent.y - cameraZ) ** 2,
      }))
      .sort((a, b) => a.dist - b.dist);

    const out: AgentView[] = [];
    for (const { agent, dist } of ranked) {
      if (must.has(agent.id) || dist <= VIEW_RADIUS * VIEW_RADIUS) {
        out.push(agent);
      }
      if (out.length >= MAX_VISIBLE) break;
    }
    return out;
  }, [agents, cameraX, cameraZ, selectedId, followId]);

  const labeled = new Set<number>();
  if (selectedId != null && selectedId >= 0) labeled.add(selectedId);
  if (typeof followId === "number") labeled.add(followId);
  visible
    .filter((a) => a.activity !== "sleeping" && a.activity !== "idle")
    .slice(0, 18)
    .forEach((a) => labeled.add(a.id));

  const installed = models ?? [];

  return (
    <group>
      {visible.map((agent, index) => {
        const rigged = index < MAX_RIGGED || agent.id === selectedId || agent.id === followId;
        return (
          <Person
            key={agent.id}
            entry={rigged ? pickModel(installed, agent.avatar_seed || `id-${agent.id}`, agent.gender) : null}
            id={agent.id}
            x={agent.x}
            z={agent.y}
            name={agent.name}
            gender={agent.gender}
            age={agent.age}
            stage={agent.stage}
            activity={agent.activity}
            profession={agent.profession}
            seed={agent.avatar_seed}
            selected={selectedId === agent.id}
            showLabel={labeled.has(agent.id)}
            thought={agent.thought}
            onSelect={onSelect}
          />
        );
      })}
      {president && (
        <Person
          entry={pickModel(installed, president.avatar_seed, president.gender)}
          id={-1}
          x={president.x}
          z={president.y}
          name={president.name}
          gender={president.gender}
          age={president.age}
          stage="adult"
          activity={president.activity}
          profession="president"
          seed={president.avatar_seed}
          selected={selectedId === -1}
          president
          showLabel
          thought={president.thought}
          onSelect={onSelect}
        />
      )}
    </group>
  );
}
