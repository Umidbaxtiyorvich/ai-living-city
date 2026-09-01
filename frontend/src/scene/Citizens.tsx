import { useMemo } from "react";
import { HumanFigure } from "./HumanFigure";
import { useWorld } from "../store/world";
import type { AgentView, PresidentView } from "../types";

const MAX_VISIBLE = 72;
const VIEW_RADIUS = 65;

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

  return (
    <group>
      {visible.map((agent) => (
        <HumanFigure
          key={agent.id}
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
          onSelect={onSelect}
        />
      ))}
      {president && (
        <HumanFigure
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
          onSelect={onSelect}
        />
      )}
    </group>
  );
}
