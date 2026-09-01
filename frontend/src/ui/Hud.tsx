import { useEffect, useState } from "react";
import { fetchAgent, postAssignment, postJson } from "../net/client";
import { useWorld, type FollowTarget } from "../store/world";
import { buildingLabel, buildingStatusLabel, professionLabel } from "./labels";
import type { AgentView, LedgerItem } from "../types";

const SPEEDS = [0, 1, 2, 5, 10, 50, 100];

const WEATHER: Record<string, string> = {
  clear: "Ochiq",
  cloudy: "Bulutli",
  rain: "Yomg'ir",
  storm: "Bo'ron",
  snow: "Qor",
  fog: "Tuman",
  heat: "Issiq",
};

const ACTIVITY: Record<string, string> = {
  idle: "kutmoqda",
  sleeping: "uxlamoqda",
  commuting: "yo'lda",
  working: "ishlamoqda",
  at_school: "maktabda",
  shopping: "xarid",
  eating: "ovqatlanmoqda",
  leisure: "dam",
  socialising: "suhbat",
  at_hospital: "shifoxona",
  seeking_job: "ish qidirmoqda",
  going_home: "uyga",
  reports: "hisobot",
  meetings: "yig'ilish",
  inspections: "ko'rik",
  planning: "reja",
  family: "oila",
  breakfast: "nonushta",
  lunch: "tushlik",
  office: "idora",
  city: "shahar",
  president: "prezident",
};

export function Hud() {
  const connected = useWorld((s) => s.connected);
  const dashboard = useWorld((s) => s.dashboard);
  const agents = useWorld((s) => s.agents);
  const president = useWorld((s) => s.president);
  const selected = useWorld((s) => s.selection);
  const follow = useWorld((s) => s.follow);
  const setFollow = useWorld((s) => s.setFollow);
  const buildings = useWorld((s) => s.buildings);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [command, setCommand] = useState("");
  const [reply, setReply] = useState("Siz — Umid Ravshanov. Buyruq yozing.");
  const [replyOk, setReplyOk] = useState(true);
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [ledger, setLedger] = useState<"tasks" | "decrees" | "laws">("tasks");

  useEffect(() => {
    if (selected?.kind !== "agent") {
      setDetail(null);
      return;
    }
    let cancelled = false;
    fetchAgent(selected.id).then((data) => {
      if (!cancelled) setDetail(data);
    });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  if (!dashboard) return null;

  const stats = dashboard.stats;
  const speed = dashboard.time.speed;
  const selectedAgent = selected?.kind === "agent" ? agents.find((a) => a.id === selected.id) : undefined;
  const selectedBuilding =
    selected?.kind === "building" ? buildings.find((b) => b.id === selected.id) : undefined;
  const decision = dashboard.current_decision;

  const player = dashboard.player;
  const role = player?.role ?? "president";

  const followTarget = async (target: FollowTarget) => {
    setFollow(target);
    const value =
      target === null ? "none" : target === "president" ? "president" : String(target);
    await postJson("/api/follow", { target: value });
  };

  const sendCommand = async (text: string, agentId?: number) => {
    const trimmed = text.trim();
    if ((!trimmed && !file) || busy) return;
    setBusy(true);
    try {
      const result = await postAssignment(
        trimmed,
        agentId ?? (selected?.kind === "agent" ? selected.id : null),
        file,
      );
      setReply(result.reply ?? "Qabul qilindi.");
      setReplyOk(result.ok !== false);
      setCommand("");
      setFile(null);
    } catch (error) {
      setReply(error instanceof Error ? error.message : "Buyruq ketmadi.");
    } finally {
      setBusy(false);
    }
  };

  const setRole = async (next: "president" | "prime_minister") => {
    await postJson("/api/role", { role: next });
  };

  return (
    <div className="hud">
      <header className="topbar">
        <div>
          <div className="brand">AI Living City</div>
          <div className="muted">
            {dashboard.city_level_name} · {connected ? "jonli" : "uzilgan"}
          </div>
        </div>
        <div className="clock">
          <strong>{dashboard.time.label}</strong>
          <span>
            {WEATHER[dashboard.weather.condition] ?? dashboard.weather.condition}
            {" · "}
            {dashboard.weather.temperature}°C
          </span>
        </div>
        <div className="speeds">
          {SPEEDS.map((value) => (
            <button
              key={value}
              className={speed === value ? "active" : ""}
              onClick={() => postJson("/api/speed", { value })}
            >
              {value === 0 ? "⏸" : `${value}×`}
            </button>
          ))}
        </div>
      </header>

      <aside className="panel left">
        <h2>Shahar</h2>
        <Stat label="Aholi" value={String(stats.population)} />
        <Stat label="Byudjet" value={money(dashboard.economy.budget)} />
        <Stat label="YaIM" value={money(dashboard.economy.gdp)} />
        <Stat label="Mamnunlik" value={`${stats.happiness.toFixed(0)}/100`} />
        <Stat label="Ishsizlik" value={pct(stats.unemployment_rate)} />
        <Stat label="Uysiz" value={String(stats.homeless)} />
        <Stat label="Qurilmoqda" value={String(stats.buildings_under_construction)} />
        {dashboard.urban && (
          <>
            <h3>Infratuzilma</h3>
            <Stat
              label="Tirbandlik"
              value={`${((dashboard.urban.traffic_congestion ?? 0) * 100).toFixed(0)}%`}
            />
            <Stat
              label="Transport"
              value={`${dashboard.urban.transport?.routes ?? 0} marshrut`}
            />
            <Stat
              label="Parkovka"
              value={
                dashboard.urban.parking?.shortage
                  ? `${dashboard.urban.parking.shortage} yetmaydi`
                  : "yetarli"
              }
            />
          </>
        )}
        <h3>Xizmatlar</h3>
        {Object.entries(stats.coverage).map(([key, value]) => (
          <Bar key={key} label={coverageLabel(key)} value={value} />
        ))}
        {president && (
          <>
            <h3>Prezident</h3>
            <p className="president-name">{president.name}</p>
            <p className="muted">Bu siz. Shahar serverda ishlayveradi.</p>
            <Stat label="Reyting" value={`${president.approval_rating.toFixed(0)}%`} />
            <div className="role-row">
              <button
                className={role === "president" ? "active" : ""}
                onClick={() => setRole("president")}
              >
                Men prezidentman
              </button>
              <button
                className={role === "prime_minister" ? "active" : ""}
                onClick={() => setRole("prime_minister")}
              >
                Men bosh vazirman
              </button>
            </div>
            <Stat
              label="Hozir"
              value={ACTIVITY[president.activity] ?? president.activity}
            />
            <button className="wide" onClick={() => followTarget("president")}>
              {follow === "president" ? "Kuzatuv yoqilgan" : "Prezidentni kuzat"}
            </button>
          </>
        )}
        {decision && (
          <div className="decision">
            <div className="muted">Joriy qaror · {decision.status}</div>
            <div>{decision.concern.description}</div>
            <div className="muted">{decision.concern.action}</div>
          </div>
        )}
        {dashboard.emergency && (
          <div className="emergency">{dashboard.emergency.text}</div>
        )}
        {player && player.standing.length > 0 && (
          <>
            <h3>Navbat</h3>
            <ul className="standing">
              {player.standing.slice(-4).reverse().map((order) => (
                <li key={order.id} className={order.done ? "done" : ""}>
                  #{order.id} {order.text}
                  {order.result ? <span>{order.result}</span> : null}
                </li>
              ))}
            </ul>
          </>
        )}
      </aside>

      <aside className="panel right">
        <h2>Kuzatuv</h2>
        <div className="role-row">
          <button className={ledger === "tasks" ? "active" : ""} onClick={() => setLedger("tasks")}>
            Topshiriq
          </button>
          <button className={ledger === "decrees" ? "active" : ""} onClick={() => setLedger("decrees")}>
            Qaror
          </button>
          <button className={ledger === "laws" ? "active" : ""} onClick={() => setLedger("laws")}>
            Qonun
          </button>
        </div>
        <LedgerList items={player?.[ledger] ?? []} />
        <h2>Voqealar</h2>
        <ul className="events">
          {[...dashboard.events].reverse().map((event) => (
            <li key={event.id} className={event.severity}>
              <span>kun {event.day}</span>
              {event.text}
            </li>
          ))}
        </ul>
        <Inspector
          agent={selectedAgent}
          president={selected?.kind === "president" ? president : null}
          building={selectedBuilding}
          detail={detail}
          onFollow={(id) => followTarget(id)}
          onOrder={(text) => sendCommand(text, selectedAgent?.id)}
        />
        <div className="admin">
          <button onClick={() => postJson("/api/admin/spawn", { count: 3 })}>
            +3 fuqaro
          </button>
          <button onClick={() => postJson("/api/admin/money", { amount: 250000 })}>
            +pul
          </button>
          <button onClick={() => postJson("/api/admin/emergency", {})}>
            Favqulodda
          </button>
          <button
            title="Yangi shahar — Egregoria uslubidagi yo'l tarmog'i bilan"
            disabled={!connected || busy}
            onClick={async () => {
              if (!connected) {
                setReply("Server bilan aloqa yo'q. Avval backendni ishga tushiring.");
                setReplyOk(false);
                return;
              }
              if (!window.confirm("Yangi shahar yaratilsinmi? Joriy saqlangan shahar o'rniga yangisi ochiladi.")) return;
              setBusy(true);
              try {
                const r = await postJson<{ reply?: string; ok?: boolean }>("/api/admin/reset", {});
                setReply(r.reply ?? "Yangi shahar yaratildi.");
                setReplyOk(r.ok !== false);
              } catch (error) {
                setReply(error instanceof Error ? error.message : "Yangi shahar yaratilmadi — server ishlamayapti.");
                setReplyOk(false);
              } finally {
                setBusy(false);
              }
            }}
          >
            Yangi shahar
          </button>
          <SaveButton />
        </div>
      </aside>

      {player?.coding && (
        <div className="code-panel">
          <div className="code-head">
            <strong>{player.coding.coder_name}</strong>
            <span>
              {player.coding.done ? "fayl saqlandi" : "kod yozmoqda"} · {player.coding.filename}
            </span>
            <button type="button" onClick={() => followTarget(player.coding!.coder_id)}>
              Kuzat
            </button>
          </div>
          <pre>
            <code>{player.coding.visible}</code>
            {!player.coding.done && <i className="cursor" />}
          </pre>
          {player.coding.done && (
            <a href={`/api/workshop/${player.coding.filename}`} target="_blank" rel="noreferrer">
              workshop/{player.coding.filename}
            </a>
          )}
        </div>
      )}

      <form
        className="command-bar"
        onSubmit={(event) => {
          event.preventDefault();
          void sendCommand(command);
        }}
      >
        <div className="command-meta">
          <strong>{role === "prime_minister" ? "Bosh vazir" : "Prezident"}</strong>
          <span className={replyOk ? "" : "command-error"}>{reply}</span>
        </div>
        <div className="command-row">
          <label className="file-btn">
            Fayl
            <input
              type="file"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <input
            value={command}
            onChange={(event) => setCommand(event.target.value)}
            placeholder={
              file
                ? `${file.name} — nima qilinsin?`
                : "Elektr o'tkaz · rasm tahrirla · hisob-kitob · qonun..."
            }
            disabled={busy}
          />
          <button type="submit" disabled={busy || (!command.trim() && !file)}>
            Buyur
          </button>
        </div>
      </form>
    </div>
  );
}

function Inspector({
  agent,
  president,
  building,
  detail,
  onFollow,
  onOrder,
}: {
  agent?: AgentView;
  president: { name: string; activity: string; approval_rating: number } | null;
  building?: { type: string; status: string; residents: number; staff: number };
  detail: Record<string, unknown> | null;
  onFollow: (id: number) => void;
  onOrder: (text: string) => void;
}) {
  if (president) {
    return (
      <div className="inspector">
        <h3>{president.name}</h3>
        <p>Prezident · {ACTIVITY[president.activity] ?? president.activity}</p>
        <p>Reyting {president.approval_rating.toFixed(0)}%</p>
      </div>
    );
  }
  if (agent) {
    const needs = (detail?.needs ?? null) as Record<string, number> | null;
    return (
      <div className="inspector">
        <h3>{agent.name}</h3>
        <p>
          {Math.round(agent.age)} yosh · {agent.gender === "female" ? "ayol" : "erkak"}
          {agent.profession ? ` · ${professionLabel(agent.profession)}` : ""}
        </p>
        {agent.desk && <p className="muted">Stol: {agent.desk}</p>}
        <p>{ACTIVITY[agent.activity] ?? agent.activity}</p>
        <p>Mamnunlik {agent.happiness.toFixed(0)}</p>
        {agent.player_order && (
          <p className="muted">
            Buyruq: {ACTIVITY[agent.player_order] ?? agent.player_order}
            {agent.player_order_note ? ` — ${agent.player_order_note}` : ""}
          </p>
        )}
        <div className="agent-orders">
          <button type="button" onClick={() => onOrder("ishga bor")}>
            Ishla
          </button>
          <button type="button" onClick={() => onOrder("uyga qayt")}>
            Uyga
          </button>
          <button type="button" onClick={() => onOrder("parkka sayr")}>
            Dam
          </button>
          <button type="button" onClick={() => onOrder("buyruqni ol")}>
            Bekor
          </button>
        </div>
        {needs && (
          <div className="needs">
            {Object.entries(needs).map(([key, value]) => (
              <Bar key={key} label={key} value={value / 100} />
            ))}
          </div>
        )}
        <button className="wide" onClick={() => onFollow(agent.id)}>
          Kuzat
        </button>
      </div>
    );
  }
  if (building) {
    return (
      <div className="inspector">
        <h3>{buildingLabel(building.type)}</h3>
        <p>{buildingStatusLabel(building.status)}</p>
        <p>
          Aholi {building.residents} · xodim {building.staff}
        </p>
      </div>
    );
  }
  return <p className="muted">Agent yoki binoni bosing.</p>;
}

function LedgerList({ items }: { items: LedgerItem[] }) {
  if (!items.length) {
    return <p className="muted">Hali yozuv yo'q.</p>;
  }
  return (
    <ul className="ledger">
      {items.map((item) => (
        <li key={`${item.kind}-${item.id}`} className={item.status}>
          <div className="ledger-head">
            <strong>#{item.id}</strong>
            <span>{statusLabel(item.status)}</span>
          </div>
          <div>{item.title}</div>
          {item.agent_name ? (
            <div className="muted">
              {item.agent_name}
              {item.created_specialist ? " · bosh vazir ochgan" : ""}
            </div>
          ) : null}
          {item.status !== "done" ? (
            <div className="bar">
              <span>{Math.round(item.progress * 100)}%</span>
              <div>
                <i style={{ width: `${Math.round(Math.max(0, Math.min(1, item.progress)) * 100)}%` }} />
              </div>
            </div>
          ) : null}
          {item.result ? <span>{item.result}</span> : null}
          {item.output_file ? (
            <a className="file-link" href={`/api/files/${item.output_file}`} target="_blank" rel="noreferrer">
              Natija: {item.output_file}
            </a>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: "navbatda",
    waiting_agent: "agent kutilyapti",
    in_progress: "bajarilmoqda",
    done: "bajarildi",
    blocked: "to'xtab qoldi",
  };
  return labels[status] ?? status;
}

function SaveButton() {
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);

  // The server autosaves every simulated day; this is for the moment the player
  // wants to be certain, right now, that the city is on disk.
  const save = async () => {
    setBusy(true);
    try {
      const result = await postJson<{ day: number }>("/api/save", {});
      setStatus(`${result.day}-kun saqlandi`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Saqlanmadi");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button onClick={save} disabled={busy}>
        {busy ? "Saqlanmoqda..." : "Saqla"}
      </button>
      {status ? <span className="muted save-status">{status}</span> : null}
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Bar({ label, value }: { label: string; value: number }) {
  return (
    <div className="bar">
      <span>{label}</span>
      <div>
        <i style={{ width: `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%` }} />
      </div>
    </div>
  );
}

function money(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} mln`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(0)} ming`;
  return n.toFixed(0);
}

function pct(n: number): string {
  return `${(n * 100).toFixed(0)}%`;
}

function coverageLabel(key: string): string {
  const labels: Record<string, string> = {
    healthcare: "Sog'liq",
    education: "Ta'lim",
    retail: "Savdo",
    food: "Oziq",
    power: "Elektr",
    security: "Xavfsizlik",
  };
  return labels[key] ?? key;
}
