import { useEffect } from "react";
import { CivHud } from "./CivHud";
import { CivScene } from "./CivScene";
import { connectCiv } from "./store";
import "./civ.css";

export function CivApp() {
  useEffect(() => connectCiv(), []);
  return (
    <div className="app">
      <CivScene />
      <CivHud />
    </div>
  );
}
