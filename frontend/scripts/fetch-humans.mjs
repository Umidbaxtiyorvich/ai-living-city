// Downloads a starter cast of rigged, animated humans into public/models/humans
// and writes the manifest the renderer reads.
//
//   npm run fetch:humans
//
// The starter models are the Mixamo-rigged samples shipped with three.js
// (examples/models/gltf). They share one skeleton, so Michelle borrows the
// Soldier's idle/walk/run clips. For a more realistic, fully CC0 cast, put the
// Quaternius "Universal Base Characters" GLBs in the same folder and list them
// in manifest.json (see README) — no code changes needed.
import { mkdir, writeFile, access } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const target = join(here, "..", "public", "models", "humans");
const SOURCE = "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r179/examples/models/gltf";

const FILES = ["Soldier.glb", "Michelle.glb", "Xbot.glb"];

const MANIFEST = [
  {
    id: "soldier",
    url: "models/humans/Soldier.glb",
    gender: "male",
    clips: { idle: "Idle", walk: "Walk", run: "Run" },
  },
  {
    id: "michelle",
    url: "models/humans/Michelle.glb",
    gender: "female",
    clipSource: "models/humans/Soldier.glb",
    clips: { idle: "Idle", walk: "Walk", run: "Run" },
  },
  {
    id: "xbot",
    url: "models/humans/Xbot.glb",
    gender: "any",
    clips: { idle: "idle", walk: "walk", run: "run" },
    tint: ["highlimbs"],
  },
];

async function exists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

await mkdir(target, { recursive: true });
for (const file of FILES) {
  const path = join(target, file);
  if (await exists(path)) {
    console.log(`= ${file} (already present)`);
    continue;
  }
  const response = await fetch(`${SOURCE}/${file}`);
  if (!response.ok) throw new Error(`${file}: HTTP ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  await writeFile(path, bytes);
  console.log(`+ ${file} (${(bytes.length / 1024 / 1024).toFixed(1)} MB)`);
}

const manifestPath = join(target, "manifest.json");
if (await exists(manifestPath)) {
  console.log("= manifest.json kept (delete it to regenerate)");
} else {
  await writeFile(manifestPath, JSON.stringify(MANIFEST, null, 2) + "\n");
  console.log("+ manifest.json");
}
