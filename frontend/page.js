"use client";
import { useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API || "http://localhost:8000";
const SAMPLES = {
  English: "Fresh Basket needs 20 kg tomato and 10 kg onion",
  "ಕನ್ನಡ": "ರಮೇಶ್ ಸ್ಟೋರ್ಸ್‌ಗೆ 20 ಕೆಜಿ ಟೊಮೇಟೊ ಮತ್ತು 10 ಕೆಜಿ ಈರುಳ್ಳಿ ಬೇಕು",
  "தமிழ்": "லட்சுமி வெஜிடபிள்ஸுக்கு 15 கிலோ தக்காளி, 5 கிலோ உருளைக்கிழங்கு வேணும்",
  "हिन्दी": "शर्मा ट्रेडर्स को 25 किलो आलू और 10 किलो प्याज़ चाहिए",
};
const LANG = { kn: "Kannada", ta: "Tamil", hi: "Hindi", en: "English" };
const inr = (n) => "₹" + Number(n).toLocaleString("en-IN");

async function api(path, opts) {
  const r = await fetch(API + path, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || "Something went wrong. Please try again.");
  return j;
}
const post = (p, b) => api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });

export default function Home() {
  const [text, setText] = useState("");
  const [role, setRole] = useState("owner");
  const [result, setResult] = useState(null);
  const [sent, setSent] = useState("");
  const [dash, setDash] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [rec, setRec] = useState(false);
  const recRef = useRef(null);

  const load = () => api("/api/dashboard").then(setDash).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  async function run(label, fn) {
    setBusy(label); setErr("");
    try { await fn(); } catch (e) { setErr(e.message); }
    setBusy("");
  }
  const prepare = () => run("Reading your order…", async () => {
    setSent(""); setResult(null);
    setResult(await post("/api/parse", { text, role, request_id: crypto.randomUUID() }));
    load();
  });
  const approve = () => run("Confirming…", async () => {
    const j = await post("/api/approve", { order_id: result.order.id, role });
    setSent(j.message); load();
  });
  const discard = () => run("Discarding…", async () => {
    await post("/api/cancel", { order_id: result.order.id, role }); setResult(null); load();
  });
  const reset = () => { setResult(null); setSent(""); setText(""); setErr(""); };

  async function toggleRec() {
    if (rec) { recRef.current.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream); const chunks = [];
      mr.ondataavailable = (e) => chunks.push(e.data);
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop()); setRec(false);
        const fd = new FormData();
        fd.append("file", new Blob(chunks, { type: mr.mimeType }), mr.mimeType.includes("mp4") ? "voice.mp4" : "voice.webm");
        run("Listening to the recording…", async () => setText((await api("/api/transcribe", { method: "POST", body: fd })).text));
      };
      mr.start(); recRef.current = mr; setRec(true);
    } catch { setErr("The microphone is blocked. Allow it in the address bar, or type the order instead."); }
  }

  const o = result?.kind === "proposal" ? result.order : null;
  const maxStock = dash ? Math.max(...dash.products.map((p) => p.stock), 1) : 1;

  return (
    <main>
      <header className="top">
        <h1>MandiMate</h1>
        <p>Say the order. Check the chit. Approve.</p>
      </header>
      <div className="layout">
        <div>
          <button className={"mic" + (rec ? " rec" : "")} onClick={toggleRec} aria-pressed={rec} aria-label={rec ? "Stop recording" : "Start recording"}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
          </button>
          <p className="miclabel" aria-live="polite">{rec ? "Listening… tap to stop" : "Tap to speak your order"}</p>

          <label htmlFor="order">Or type it, in Kannada, Tamil, Hindi or English</label>
          <textarea id="order" value={text} onChange={(e) => setText(e.target.value)} placeholder="Fresh Basket needs 20 kg tomato and 10 kg onion" />
          <div className="row">
            <button className="go" disabled={!!busy || !text.trim()} onClick={prepare}>{busy || "Prepare order"}</button>
            <div className="seg" role="group" aria-label="Acting as">
              {["owner", "staff", "viewer"].map((r) => <button key={r} aria-pressed={role === r} onClick={() => setRole(r)}>{r}</button>)}
            </div>
          </div>
          <div className="ex"><span>Examples</span>{Object.entries(SAMPLES).map(([k, v]) => <button key={k} onClick={() => setText(v)}>{k}</button>)}</div>
          {err && <p className="err" role="alert">{err}</p>}

          {result?.kind === "clarify" && <p className="note">{result.message}{result.warnings?.map((w, i) => <><br key={i} />{w}</>)}</p>}
          {result?.kind === "stock" && <p className="note">{result.lines.map((l) => `${l.name}: ${l.stock} kg in stock`).join(" · ")}</p>}

          {o && (
            <section className="parchi" aria-live="polite">
              <header><h2>{o.vendors.name}</h2><span className="chip">Messages in {LANG[o.vendors.language]}</span></header>
              <table>
                <thead><tr><th>Item</th><th className="num">Kg</th><th className="num">Rate</th><th className="num">Amount</th></tr></thead>
                <tbody>{o.order_items.map((i) => (
                  <tr key={i.product_id}><td>{i.products.name}</td><td className="num">{i.quantity}</td><td className="num">{inr(i.unit_price)}</td><td className="num">{inr(i.quantity * i.unit_price)}</td></tr>
                ))}</tbody>
                <tfoot><tr><td colSpan={3}>Total</td><td className="num">{inr(o.total)}</td></tr></tfoot>
              </table>
              {result.warnings.map((w, i) => <p key={i} className="note">{w}</p>)}
              {sent ? (<>
                <div className="stamp">Confirmed</div>
                <div className="bubble"><small>Sent to {o.vendors.name}</small>{sent}</div>
                <button className="again" onClick={reset}>Start a new order</button>
              </>) : (
                <div className="actions">
                  <button className="go" disabled={!!busy} onClick={approve}>{busy || "Approve order"}</button>
                  <button className="alt" disabled={!!busy} onClick={discard}>Discard</button>
                </div>
              )}
            </section>
          )}
        </div>

        <aside>
          {dash ? (<>
            <div className="slate">
              <h3>Godown</h3>
              {dash.products.map((p) => (
                <div key={p.name} className={"srow" + (p.stock < 100 ? " low" : "")}>
                  <span>{p.name}</span>
                  <div className="bar"><i style={{ width: (p.stock / maxStock) * 100 + "%" }} /></div>
                  <b className="num">{p.stock} kg</b>
                </div>
              ))}
            </div>
            <div className="khata">
              <h3>Khata: who owes you</h3>
              <table><tbody>{dash.vendors.map((v) => (
                <tr key={v.name}><td>{v.name}</td><td><span className="chip">{LANG[v.language]}</span></td><td className="num"><b>{inr(v.balance_due)}</b></td></tr>
              ))}</tbody></table>
            </div>
            <details>
              <summary>Recent orders and activity</summary>
              {dash.orders.map((x) => <p key={x.id} className="log">#{x.id.slice(0, 6)} · {x.vendors?.name} · {x.status} · {inr(x.total)}</p>)}
              <hr />
              {dash.audit.map((a) => <p key={a.id} className="log">{new Date(a.created_at).toLocaleTimeString()} · {a.actor} · {a.action}</p>)}
            </details>
          </>) : <p className="log">Loading your godown…</p>}
        </aside>
      </div>
    </main>
  );
}
