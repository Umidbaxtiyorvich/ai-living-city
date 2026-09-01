import type { Snapshot } from "../types";
import { useWorld } from "../store/world";

let socket: WebSocket | null = null;
let retries = 0;
let refCount = 0;
let timer: number | null = null;

function wsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws`;
}

function open() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }
  const ws = new WebSocket(wsUrl());
  socket = ws;

  ws.onopen = () => {
    retries = 0;
    useWorld.getState().setConnected(true);
  };
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data) as Snapshot;
    useWorld.getState().apply(msg);
  };
  ws.onclose = () => {
    useWorld.getState().setConnected(false);
    if (socket === ws) socket = null;
    if (refCount <= 0) return;
    const wait = Math.min(8_000, 600 * 2 ** retries);
    retries += 1;
    timer = window.setTimeout(open, wait);
  };
}

export function connectWorld(): () => void {
  refCount += 1;
  open();
  return () => {
    refCount -= 1;
    if (refCount > 0) return;
    if (timer != null) {
      window.clearTimeout(timer);
      timer = null;
    }
    socket?.close();
    socket = null;
  };
}

export async function postJson<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  const data = text ? (JSON.parse(text) as T) : ({} as T);
  if (!res.ok) {
    throw new Error(typeof data === "object" && data && "detail" in data
      ? String((data as { detail: unknown }).detail)
      : res.statusText);
  }
  return data;
}

export async function postAssignment(
  text: string,
  agentId?: number | null,
  file?: File | null,
): Promise<{ ok?: boolean; reply?: string }> {
  const body = new FormData();
  body.append("text", text);
  if (agentId != null) body.append("agent_id", String(agentId));
  if (file) body.append("file", file);
  const res = await fetch("/api/assignment", { method: "POST", body });
  const raw = await res.text();
  const data = raw ? JSON.parse(raw) : {};
  if (!res.ok) {
    throw new Error(data.detail ? String(data.detail) : res.statusText);
  }
  return data;
}

export async function fetchAgent(id: number) {
  const res = await fetch(`/api/agent/${id}`);
  if (!res.ok) return null;
  return res.json();
}
