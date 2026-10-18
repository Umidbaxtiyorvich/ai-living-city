import { useEffect, useState } from "react";
import { civPost, useCiv } from "./store";

const SPEEDS = [0, 1, 2, 5, 10, 25, 50];

const KIND_ICON: Record<string, string> = {
  era: "🔥",
  discovery: "💡",
  wedding: "💍",
  birth: "👶",
  death: "🕯️",
  build: "🏠",
  settlement: "🏘️",
  politics: "🏛️",
  life: "•",
};

const NEED_LABEL: Record<string, string> = {
  hunger: "To'qlik",
  energy: "Kuch",
  social: "Muloqot",
  health: "Sog'liq",
};

const SKILL_LABEL: Record<string, string> = {
  gathering: "terish",
  woodcutting: "o'tin",
  stonework: "tosh",
  building: "qurilish",
  farming: "dehqonchilik",
  thinking: "tafakkur",
};

interface PersonDetail {
  id: number;
  name: string;
  gender: string;
  age: number;
  task_label: string;
  thought: string;
  awareness: number;
  wisdom: number;
  needs: Record<string, number>;
  happiness: number;
  skills: Record<string, number>;
  goals: { kind: string; text: string; progress: number }[];
  memories: string[];
  partner: string | null;
  children: number;
  settlement: string | null;
  home: string | null;
  discoveries: number;
  buildings_built: number;
  alive: boolean;
}

function hourLabel(hour: number): string {
  const h = Math.floor(hour);
  const m = Math.floor((hour - h) * 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function Bar({ label, value }: { label: string; value: number }) {
  const v = Math.max(0, Math.min(1, value));
  return (
    <div className="civ-bar">
      <span>{label}</span>
      <i>
        <b style={{ width: `${v * 100}%`, background: v < 0.3 ? "#e0664a" : v < 0.6 ? "#e6b84a" : "#6fd39a" }} />
      </i>
    </div>
  );
}

function Inspector() {
  const selected = useCiv((s) => s.selected);
  const buildings = useCiv((s) => s.buildings);
  const setFollow = useCiv((s) => s.setFollow);
  const follow = useCiv((s) => s.follow);
  const [detail, setDetail] = useState<PersonDetail | null>(null);

  useEffect(() => {
    setDetail(null);
    if (selected == null || selected <= 0) return;
    let alive = true;
    const load = () =>
      fetch(`/api/civ/person/${selected}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => alive && setDetail(data))
        .catch(() => undefined);
    void load();
    const timer = window.setInterval(load, 1000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [selected]);

  if (selected != null && selected < 0) {
    const b = buildings.find((item) => item.id === -selected);
    if (!b) return null;
    return (
      <div className="civ-panel civ-inspector">
        <h3>{b.name}</h3>
        <p className="muted">{b.complete ? "Qurilgan" : `Qurilmoqda — ${Math.round(b.progress * 100)}%`}</p>
        {b.category === "home" && <p>Yashovchilar: {b.residents}</p>}
        {b.kind === "field" && <Bar label="Hosil" value={b.growth} />}
      </div>
    );
  }
  if (!detail) return null;
  return (
    <div className="civ-panel civ-inspector">
      <h3>{detail.name}</h3>
      <p className="muted">
        {Math.floor(detail.age)} yosh · {detail.gender === "female" ? "ayol" : "erkak"} · {detail.settlement ?? "—"}
      </p>
      <p className="civ-doing">{detail.task_label}</p>
      {detail.thought && <p className="civ-thought">💭 {detail.thought}</p>}
      {Object.entries(detail.needs).map(([key, value]) => (
        <Bar key={key} label={NEED_LABEL[key] ?? key} value={value / 100} />
      ))}
      <Bar label="Ong" value={detail.awareness / 100} />
      <p className="muted small">
        {detail.partner ? `Turmush o'rtog'i: ${detail.partner}` : "Turmush qurmagan"} · farzandlar: {detail.children}
        <br />
        Uyi: {detail.home ?? "yo'q"} · qurgan binolari: {detail.buildings_built}
        {detail.discoveries > 0 ? ` · kashfiyotlar: ${detail.discoveries}` : ""}
      </p>
      {detail.goals.length > 0 && (
        <>
          <h4>Orzulari</h4>
          <ul className="civ-goals">
            {detail.goals.map((goal) => (
              <li key={goal.kind}>
                {goal.text}
                <i style={{ width: `${Math.round(goal.progress * 100)}%` }} />
              </li>
            ))}
          </ul>
        </>
      )}
      <h4>Mahorati</h4>
      <p className="muted small">
        {Object.entries(detail.skills)
          .slice(0, 4)
          .map(([k, v]) => `${SKILL_LABEL[k] ?? k} ${v}`)
          .join(" · ")}
      </p>
      {detail.memories.length > 0 && (
        <>
          <h4>Xotiralari</h4>
          <ul className="civ-memories">
            {[...detail.memories].reverse().slice(0, 4).map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </>
      )}
      <button className="civ-wide" onClick={() => setFollow(follow === detail.id ? null : detail.id)}>
        {follow === detail.id ? "Kuzatishni to'xtatish" : "Kuzatish"}
      </button>
    </div>
  );
}

export function CivHud() {
  const stats = useCiv((s) => s.stats);
  const time = useCiv((s) => s.time);
  const speed = useCiv((s) => s.speed);
  const settlements = useCiv((s) => s.settlements);
  const chronicle = useCiv((s) => s.chronicle);
  const connected = useCiv((s) => s.connected);
  const flyTo = useCiv((s) => s.flyTo);
  const select = useCiv((s) => s.select);
  const people = useCiv((s) => s.people);
  const [busy, setBusy] = useState(false);

  if (!stats || !time) return null;

  const followRandom = () => {
    const adults = people.filter((p) => p[4] === "adult" && p[3] !== "sleep");
    const pick = adults[Math.floor(Math.random() * adults.length)] ?? people[0];
    if (!pick) return;
    select(pick[0]);
    useCiv.getState().setFollow(pick[0]);
  };

  return (
    <div className="civ-hud">
      <header className="civ-panel civ-top">
        <div className="civ-title">
          <strong>{stats.era}</strong>
          <span>
            {time.year}-yil · {time.day_of_year}-kun · {hourLabel(time.hour)} {time.night ? "🌙" : "☀️"}
          </span>
        </div>
        <div className="civ-speeds">
          {SPEEDS.map((value) => (
            <button key={value} className={speed === value ? "on" : ""} onClick={() => civPost("/api/civ/speed", { value })}>
              {value === 0 ? "⏸" : `${value}×`}
            </button>
          ))}
        </div>
        {!connected && <span className="civ-offline">aloqa yo'q…</span>}
      </header>

      <aside className="civ-panel civ-left">
        <h2>Xalq</h2>
        <div className="civ-stats">
          <div><b>{stats.population}</b><span>aholi</span></div>
          <div><b>{stats.families}</b><span>oila</span></div>
          <div><b>{stats.births}</b><span>tug'ildi</span></div>
          <div><b>{stats.deaths}</b><span>vafot</span></div>
          <div><b>{stats.homes}</b><span>uy</span></div>
          <div><b>{stats.sites}</b><span>qurilmoqda</span></div>
        </div>
        <Bar label="Baxt" value={stats.happiness / 100} />
        <Bar label="Ong" value={stats.awareness / 100} />
        <h3>Kashfiyotlar</h3>
        {stats.researching ? (
          <>
            <p className="muted small">O'ylab topilmoqda: {stats.researching.name}</p>
            <Bar label="" value={stats.researching.progress} />
          </>
        ) : (
          <p className="muted small">Barcha bilimlar egallangan</p>
        )}
        <div className="civ-chips">
          {stats.known.map((tech) => (
            <span key={tech.key}>{tech.name}</span>
          ))}
        </div>
        <h3>Manzillar</h3>
        <ul className="civ-places">
          {settlements.map((s) => (
            <li key={s.id} onClick={() => flyTo(s.x, s.y)}>
              <strong>{s.name}</strong>
              <span>
                {s.rank} · {s.population} kishi
              </span>
              <em>
                🍎 {s.storage.food} · 🪵 {s.storage.wood} · 🪨 {s.storage.stone}
              </em>
            </li>
          ))}
        </ul>
        <div className="civ-row">
          <button onClick={followRandom}>Birovni kuzat</button>
          <button
            disabled={busy}
            onClick={async () => {
              if (!window.confirm("Yangi dunyo — 10 kishi bilan qaytadan boshlansinmi?")) return;
              setBusy(true);
              await civPost("/api/civ/reset");
              setBusy(false);
            }}
          >
            Yangi dunyo
          </button>
        </div>
      </aside>

      <aside className="civ-panel civ-right">
        <h2>Xronika</h2>
        <ul className="civ-chronicle">
          {[...chronicle].reverse().map((item, i) => (
            <li key={`${item.day}-${i}`} className={`k-${item.kind}`}>
              <span>
                {KIND_ICON[item.kind] ?? "•"} {item.year}-yil
              </span>
              {item.text}
            </li>
          ))}
        </ul>
      </aside>

      <Inspector />
    </div>
  );
}
