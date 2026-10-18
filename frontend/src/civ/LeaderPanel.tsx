import { useState } from "react";
import { act, useCiv, type Petition } from "./store";

const KIND_ICON: Record<string, string> = {
  no_wood: "🪵",
  no_stone: "🪨",
  no_food: "🍎",
  famine: "🍞",
  no_plot: "🏠",
  sick: "🤒",
  lonely: "💔",
};

const EXAMPLES = [
  "Hammaga dehqonchilikni o'rgataman",
  "O'rmonni asranglar, ko'chat ekinglar",
  "Bolalarni o'qitinglar",
  "Zaxira to'planglar",
  "Hashar qilinglar, bir-biringizga yordam beringlar",
];

function Answer({ petition }: { petition: Petition }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState("");
  const send = async () => {
    if (!text.trim()) return;
    setBusy(true);
    const result = await act({ action: "say", text, petition: petition.id });
    setReply(result.reply ?? "");
    if (result.ok) setText("");
    setBusy(false);
  };
  return (
    <div className="civ-answer">
      <input
        value={text}
        placeholder="Javobingiz… (masalan: shimolga borib o'tin kes)"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") void send();
          e.stopPropagation();
        }}
        disabled={busy}
      />
      <button onClick={send} disabled={busy || !text.trim()}>
        Javob
      </button>
      {reply && <p className="civ-reply">{reply}</p>}
    </div>
  );
}

/** Problems the people bring to their leader, and the leader's teachings. */
export function LeaderPanel({ onClose }: { onClose: () => void }) {
  const petitions = useCiv((s) => s.petitions);
  const customs = useCiv((s) => s.customs);
  const select = useCiv((s) => s.select);
  const setFollow = useCiv((s) => s.setFollow);
  const [speech, setSpeech] = useState("");
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState("");
  const open = petitions.filter((p) => p.status === "open");
  const closed = petitions.filter((p) => p.status !== "open").slice(0, 4);

  const speak = async (text: string) => {
    if (!text.trim()) return;
    setBusy(true);
    const result = await act({ action: "say", text });
    setReply(result.reply ?? "");
    if (result.ok) setSpeech("");
    setBusy(false);
  };

  return (
    <div className="civ-panel civ-leader">
      <div className="civ-leader-head">
        <h2>Rahbar sifatida</h2>
        <button onClick={onClose}>✕</button>
      </div>
      <h3>Murojaatlar {open.length ? `(${open.length})` : ""}</h3>
      {open.length === 0 && <p className="muted small">Hozircha hech kim muammo bilan kelmadi.</p>}
      {open.map((p) => (
        <div key={p.id} className={`civ-petition ${p.arrived ? "here" : ""}`}>
          <div className="civ-petition-top">
            <button
              className="civ-link"
              onClick={() => {
                select(p.person_id);
                setFollow(p.person_id);
              }}
            >
              {KIND_ICON[p.kind] ?? "❓"} {p.name}
            </button>
            <span>{p.arrived ? "yoningizda" : "yo'lda…"}</span>
          </div>
          <p>«{p.text}»</p>
          <Answer petition={p} />
        </div>
      ))}
      {closed.length > 0 && (
        <>
          <h3>Hal qilinganlar</h3>
          {closed.map((p) => (
            <div key={p.id} className="civ-petition done">
              <strong>
                {KIND_ICON[p.kind] ?? "❓"} {p.name}
              </strong>
              {p.status === "solved" ? (
                <p className="small">
                  Siz: «{p.answer}» → {p.reply}
                </p>
              ) : (
                <p className="small muted">Javobsiz qoldi — o'zlari hal qilishga urindi.</p>
              )}
            </div>
          ))}
        </>
      )}
      <h3>Xalqqa so'z / o'rgatish</h3>
      <div className="civ-answer">
        <input
          value={speech}
          placeholder="Masalan: hammaga dehqonchilikni o'rgataman"
          onChange={(e) => setSpeech(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void speak(speech);
            e.stopPropagation();
          }}
          disabled={busy}
        />
        <button onClick={() => speak(speech)} disabled={busy || !speech.trim()}>
          Ayt
        </button>
      </div>
      <div className="civ-examples">
        {EXAMPLES.map((example) => (
          <button key={example} onClick={() => setSpeech(example)}>
            {example}
          </button>
        ))}
      </div>
      {reply && <p className="civ-reply">{reply}</p>}
      {customs.length > 0 && (
        <>
          <h3>Siz o'rgatgan odatlar</h3>
          <ul className="civ-customs">
            {customs.map((c) => (
              <li key={c.key}>✔ {c.text}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
