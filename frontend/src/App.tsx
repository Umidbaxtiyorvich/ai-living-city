import { useEffect, useRef, useState } from "react";
import { CityScene } from "./scene/CityScene";
import { Hud } from "./ui/Hud";
import { connectWorld, postJson } from "./net/client";
import { useWorld } from "./store/world";
import { CivApp } from "./civ/CivApp";

/** The server runs one world: a civilization grown from ten people, or the managed city. */
export function App() {
  const [mode, setMode] = useState<string | null>(null);
  useEffect(() => {
    fetch("/api/mode")
      .then((r) => (r.ok ? r.json() : { mode: "civ" }))
      .then((data: { mode?: string }) => setMode(data.mode ?? "civ"))
      .catch(() => setMode("civ"));
  }, []);
  if (mode === null) return <div className="loading">Yuklanmoqda…</div>;
  return mode === "city" ? <CityApp /> : <CivApp />;
}

function CityApp() {
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
