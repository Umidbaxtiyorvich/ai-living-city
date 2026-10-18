import { useEffect } from "react";
import { CivHud } from "./CivHud";
import { CivScene, view } from "./CivScene";
import { bodies } from "./People";
import { act, connectCiv, useCiv } from "./store";
import "./civ.css";

const KEYS: Record<string, [number, number]> = {
  w: [0, -1], arrowup: [0, -1], s: [0, 1], arrowdown: [0, 1],
  a: [-1, 0], arrowleft: [-1, 0], d: [1, 0], arrowright: [1, 0],
  "ц": [0, -1], "ы": [0, 1], "ф": [-1, 0], "в": [1, 0],
};

/** WASD walks the player's character, relative to where the camera looks. */
function useWalkKeys() {
  useEffect(() => {
    const held = new Set<string>();
    const down = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
      const key = event.key.toLowerCase();
      if (KEYS[key]) {
        held.add(key);
        event.preventDefault();
      }
      if (key === "escape") useCiv.getState().setPlacing(null);
    };
    const up = (event: KeyboardEvent) => held.delete(event.key.toLowerCase());
    const timer = window.setInterval(() => {
      if (!held.size) return;
      const { playerId } = useCiv.getState();
      const me = playerId != null ? bodies.get(playerId) : undefined;
      if (!me) return;
      let fx = 0;
      let fz = 0;
      for (const key of held) {
        fx += KEYS[key][0];
        fz += KEYS[key][1];
      }
      if (!fx && !fz) return;
      // Rotate the key direction by the camera heading.
      const a = view.azimuth;
      const dx = fx * Math.cos(a) + fz * Math.sin(a);
      const dz = -fx * Math.sin(a) + fz * Math.cos(a);
      const len = Math.hypot(dx, dz) || 1;
      void act({ action: "goto", x: me.x + (dx / len) * 3, y: me.z + (dz / len) * 3 });
    }, 300);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);
}

export function CivApp() {
  useEffect(() => connectCiv(), []);
  useWalkKeys();
  return (
    <div className="app">
      <CivScene />
      <CivHud />
    </div>
  );
}
