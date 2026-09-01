import { useEffect, useRef } from "react";
import { CityScene } from "./scene/CityScene";
import { Hud } from "./ui/Hud";
import { connectWorld, postJson } from "./net/client";
import { useWorld } from "./store/world";

export function App() {
  useEffect(() => connectWorld(), []);
  const president = useWorld((s) => s.president);
  const setFollow = useWorld((s) => s.setFollow);
  const booted = useRef(false);

  useEffect(() => {
    if (booted.current || !president) return;
    booted.current = true;
    setFollow("president");
    void postJson("/api/follow", { target: "president" });
  }, [president, setFollow]);

  return (
    <div className="app">
      <CityScene />
      <Hud />
    </div>
  );
}
