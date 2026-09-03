const BASE = "/api";

async function errText(r) {
  try {
    const j = await r.json();
    return j.detail || j.error || JSON.stringify(j);
  } catch {
    return `${r.status} ${r.statusText}`;
  }
}

export async function getJSON(path) {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(await errText(r));
  return r.json();
}

export async function postJSON(path, body) {
  const r = await fetch(BASE + path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(await errText(r));
  return r.json();
}

export async function del(path) {
  const r = await fetch(BASE + path, { method: "DELETE" });
  if (!r.ok) throw new Error(await errText(r));
  return r.json();
}

export async function createRun(file, opts, source) {
  const fd = new FormData();
  fd.append("image", file, file.name || "capture.jpg");
  Object.entries(opts).forEach(([k, v]) => fd.append(k, String(v)));
  fd.append("source", source);
  const r = await fetch(BASE + "/runs", { method: "POST", body: fd });
  if (!r.ok) throw new Error(await errText(r));
  return r.json();
}

export const fileUrl = (id, name) => `${BASE}/runs/${encodeURIComponent(id)}/files/${encodeURIComponent(name)}`;
