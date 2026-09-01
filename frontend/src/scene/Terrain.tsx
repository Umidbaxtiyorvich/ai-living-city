import { useEffect, useMemo } from "react";
import { CanvasTexture, LinearFilter, SRGBColorSpace } from "three";
import type { TileMap } from "../types";
import { expandDistricts, expandRoadLevels, expandTiles } from "./WorldProps";
import { roadColorForLevel } from "./StreetProps";

const DISTRICT_TINT: Record<string, [number, number, number]> = {
  residential: [10, 16, 6],
  business: [18, 14, -4],
  city_center: [14, 10, 18],
  industrial: [16, 6, -10],
  shopping: [22, 18, 0],
  office: [12, 14, 12],
  hospital: [8, 18, 14],
  school: [10, 16, 10],
  park: [6, 20, 8],
  farm: [14, 10, -6],
};

const TILE_COLORS: Record<string, [number, number, number]> = {
  grass: [78, 140, 62],
  road: [52, 52, 56],
  sidewalk: [168, 162, 152],
  buildable: [110, 150, 78],
  water: [42, 110, 168],
  park: [52, 158, 82],
  building: [120, 110, 98],
  forest: [32, 92, 44],
  reserved: [90, 88, 60],
};

export function Terrain({ tiles }: { tiles: TileMap }) {
  const texture = useMemo(() => paintTiles(tiles), [tiles]);
  useEffect(() => () => texture.dispose(), [texture]);
  const w = tiles.width;
  const h = tiles.height;

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[w / 2, 0, h / 2]} receiveShadow>
      <planeGeometry args={[w, h]} />
      <meshStandardMaterial map={texture} roughness={0.9} metalness={0} />
    </mesh>
  );
}

function paintTiles(tiles: TileMap): CanvasTexture {
  const scale = 8;
  const canvas = document.createElement("canvas");
  canvas.width = tiles.width * scale;
  canvas.height = tiles.height * scale;
  const ctx = canvas.getContext("2d")!;
  const types = expandTiles(tiles);
  const roadLevels = expandRoadLevels(tiles);
  const districts = expandDistricts(tiles);

  for (let y = 0; y < tiles.height; y++) {
    for (let x = 0; x < tiles.width; x++) {
      const idx = y * tiles.width + x;
      const type = types[idx];
      const roadLevel = roadLevels[idx];
      const district = districts[idx];
      const [r, g, b] = TILE_COLORS[type] ?? TILE_COLORS.grass;
      const tint = DISTRICT_TINT[district] ?? [0, 0, 0];
      const n = ((x * 13 + y * 7) % 11) - 5;
      const applyTint = type === "grass" || type === "buildable" || type === "park";
      ctx.fillStyle = `rgb(${clamp(r + n + (applyTint ? tint[0] : 0))},${clamp(g + n + (applyTint ? tint[1] : 0))},${clamp(b + n + (applyTint ? tint[2] : 0))})`;
      ctx.fillRect(x * scale, y * scale, scale, scale);
      if (type === "road" && roadLevel > 0) {
        const rc = roadColorForLevel(roadLevel);
        if (rc) {
          ctx.fillStyle = rc;
          ctx.fillRect(x * scale, y * scale, scale, scale);
        }
        const laneW = Math.max(1, (5 - roadLevel) * 0.5);
        ctx.fillStyle = "rgba(230,210,90,0.4)";
        ctx.fillRect(x * scale + scale / 2 - laneW, y * scale, laneW * 2, scale);
      } else if (type === "road") {
        ctx.fillStyle = "rgba(230,210,90,0.35)";
        ctx.fillRect(x * scale + scale / 2 - 0.7, y * scale, 1.4, scale);
      }
      if (type === "water") {
        ctx.fillStyle = "rgba(180,220,255,0.18)";
        ctx.fillRect(x * scale, y * scale + 3, scale, 2);
      }
    }
  }

  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  texture.minFilter = LinearFilter;
  texture.magFilter = LinearFilter;
  texture.needsUpdate = true;
  return texture;
}

function clamp(n: number): number {
  return Math.max(0, Math.min(255, n));
}
