import { useEffect, useMemo, useState } from "react";
import "./app.css";

const DEFAULT_API = "http://127.0.0.1:8080";

/* ---------------- UI helpers ---------------- */

function badgeColor(status) {
  if (status === "done") return "#12b981";
  if (status === "error") return "#ef4444";
  return "#f59e0b";
}

function Badge({ status }) {
  return (
    <span
      style={{
        padding: "2px 8px",
        borderRadius: 999,
        color: "#fff",
        background: badgeColor(status),
        fontSize: 12,
      }}
    >
      {status}
    </span>
  );
}

function FileCard({ f }) {
  return (
    <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 8 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 6,
        }}
      >
        <code>{f.path}</code>
        <button
          onClick={() => navigator.clipboard.writeText(f.content || "")}
          title="Copy content"
          style={{ padding: "4px 8px" }}
        >
          Copy
        </button>
      </div>
      <pre
        style={{
          background: "#0b1020",
          color: "#e5e7eb",
          padding: 8,
          borderRadius: 6,
          maxHeight: 220,
          overflow: "auto",
        }}
      >
{f.content}
      </pre>
    </div>
  );
}

/** Show subjobs from /results/{id}?expand=1 (for "pipeline"). */
function Subjobs({ result }) {
  const subs = result?.result?.subjobs || {};
  const details = result?.result?.subjobs_detail || null;
  const names = Object.keys(subs);
  if (names.length === 0) return null;

  return (
    <div style={{ marginTop: 12 }}>
      <h4 style={{ margin: "8px 0" }}>Subjobs</h4>
      <div style={{ display: "grid", gap: 8 }}>
        {names.map((name) => {
          const jid = subs[name];
          const d = details?.[name];
          const st = typeof d === "object" && d ? (d.status || "?") : "…";
          return (
            <div
              key={name}
              style={{ border: "1px solid #eee", borderRadius: 8, padding: 8 }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: 6,
                }}
              >
                <div>
                  <strong>{name}</strong> &nbsp; <code>#{jid}</code>
                </div>
                <div>
                  <span style={{ fontSize: 12, opacity: 0.75 }}>{st}</span>
                </div>
              </div>
              {d && (
                <pre
                  style={{
                    background: "#0b1020",
                    color: "#e5e7eb",
                    padding: 8,
                    borderRadius: 6,
                    maxHeight: 220,
                    overflow: "auto",
                  }}
                >
{JSON.stringify(d, null, 2)}
                </pre>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ---------------- App ---------------- */

export default function App() {
  // simple settings (can move to a drawer later)
  const [apiUrl, setApiUrl] = useState(
    localStorage.getItem("apiUrl") || DEFAULT_API
  );
  const [apiKey, setApiKey] = useState(localStorage.getItem("apiKey") || "dev");

  const [health, setHealth] = useState(null);
  const [task, setTask] = useState("plan");
  const [idea, setIdea] = useState("demo");
  const [moduleName, setModuleName] = useState("hello_mod");

  const [jobId, setJobId] = useState("");
  const [result, setResult] = useState(null);
  const [rawMode, setRawMode] = useState(false);
  const [recent, setRecent] = useState([]);
  const [watching, setWatching] = useState(false);

  // persist settings
  useEffect(() => {
    localStorage.setItem("apiUrl", apiUrl);
  }, [apiUrl]);
  useEffect(() => {
    localStorage.setItem("apiKey", apiKey);
  }, [apiKey]);

  // boot
  useEffect(() => {
    fetch(`${apiUrl}/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null));
    const iv = setInterval(() => {
      fetch(`${apiUrl}/tasks`)
        .then((r) => r.json())
        .then((d) => setRecent(d.items ?? []))
        .catch(() => {});
    }, 1500);
    return () => clearInterval(iv);
  }, [apiUrl]);

  async function submitTask() {
    const payload = { idea, module: moduleName };
    const r = await fetch(`${apiUrl}/tasks`, {
      method: "POST",
      headers: { "content-type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify({ task, payload }),
    });
    const d = await r.json();
    const id = String(d.job_id || "");
    setJobId(id);
    setResult(null);
    if (id) {
      setWatching(true);
      autoPoll(id);
    }
  }

  async function pollOnce(id) {
    const r = await fetch(`${apiUrl}/results/${id}?expand=1`);
    const d = await r.json();
    return d.item || d;
  }

  async function autoPoll(id) {
    let keep = true;
    while (keep) {
      const item = await pollOnce(id);
      setResult(item);
      const status = item?.status;
      if (status === "done" || status === "error") {
        keep = false;
        setWatching(false);
      } else {
        await new Promise((res) => setTimeout(res, 800));
      }
    }
  }

  async function poll() {
    if (!jobId) return;
    setWatching(true);
    await autoPoll(jobId);
  }

  async function retryLast() {
    if (!result) return;
    const lastTask = result.task;
    const lastPayload = result.payload || {};
    const r = await fetch(`${apiUrl}/tasks`, {
      method: "POST",
      headers: { "content-type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify({ task: lastTask, payload: lastPayload }),
    });
    const d = await r.json();
    const id = String(d.job_id || "");
    setJobId(id);
    setResult(null);
    if (id) {
      setWatching(true);
      autoPoll(id);
    }
  }

  const pretty = useMemo(
    () => (result ? JSON.stringify(result, null, 2) : ""),
    [result]
  );

  const files = useMemo(() => {
    // supports both "codegen" and older "generate_code" task names
    const f = result?.result?.files;
    return Array.isArray(f) ? f : [];
  }, [result]);

  return (
    <div
      style={{
        fontFamily: "system-ui, sans-serif",
        padding: 16,
        maxWidth: 980,
        margin: "0 auto",
      }}
    >
      <header
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto",
          alignItems: "center",
          gap: 12,
          marginBottom: 12,
        }}
      >
        <h1 style={{ margin: 0 }}>Velu Console</h1>
        <span style={{ opacity: 0.7 }}>
          Health: {health?.ok ? "OK" : "…"} {health?.app ? `(${health.app})` : ""}
        </span>
      </header>

      {/* Settings bar */}
      <section
        style={{
          display: "grid",
          gap: 8,
          gridTemplateColumns: "1fr 1fr auto",
          alignItems: "end",
          marginBottom: 12,
        }}
      >
        <div>
          <label>API URL</label>
          <input
            value={apiUrl}
            onChange={(e) => setApiUrl(e.target.value)}
            placeholder="http://127.0.0.1:8080"
          />
        </div>
        <div>
          <label>API Key</label>
          <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </div>
        <div style={{ fontSize: 12, opacity: 0.7, paddingBottom: 8 }}>
          (saved locally)
        </div>
      </section>

      <section
        style={{
          display: "grid",
          gap: 12,
          border: "1px solid #e5e7eb",
          padding: 16,
          borderRadius: 12,
          marginBottom: 16,
        }}
      >
        <h2 style={{ margin: 0 }}>Submit</h2>
        <label>Task</label>
        <select value={task} onChange={(e) => setTask(e.target.value)}>
          <option value="plan">plan</option>
          <option value="codegen">codegen</option>
          <option value="pipeline">pipeline</option>
        </select>

        <label>Idea</label>
        <input value={idea} onChange={(e) => setIdea(e.target.value)} />

        <label>Module</label>
        <input value={moduleName} onChange={(e) => setModuleName(e.target.value)} />

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button onClick={submitTask}>Submit</button>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              marginLeft: "auto",
            }}
          >
            <input
              type="checkbox"
              checked={rawMode}
              onChange={(e) => setRawMode(e.target.checked)}
            />
            show raw JSON only
          </label>
        </div>
      </section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16,
          alignItems: "start",
        }}
      >
        <div style={{ border: "1px solid #e5e7eb", padding: 16, borderRadius: 12 }}>
          <h3 style={{ marginTop: 0 }}>Watch result</h3>
          <label>Job ID</label>
          <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
            <input value={jobId} onChange={(e) => setJobId(e.target.value)} />
            <button onClick={poll} disabled={!jobId || watching}>
              {watching ? "Watching…" : "Watch"}
            </button>
            {result?.status === "error" && (
              <button
                onClick={retryLast}
                title="Re-enqueue the same task/payload"
              >
                Retry
              </button>
            )}
          </div>

          {result && !rawMode && (
            <>
              <div style={{ marginBottom: 8 }}>
                <strong>Task:</strong> {result.task} &nbsp;
                <Badge status={result.status} />
              </div>
              <div style={{ marginBottom: 8 }}>
                <strong>Payload:</strong>{" "}
                <code
                  style={{
                    background: "#f7f7f7",
                    padding: "2px 6px",
                    borderRadius: 6,
                  }}
                >
                  {JSON.stringify(result.payload)}
                </code>
              </div>

              {/* Subjobs (for pipeline) */}
              <Subjobs result={result} />

              {/* Files (for codegen / generate_code) */}
              {files.length > 0 && (
                <div style={{ display: "grid", gap: 8, marginBottom: 8 }}>
                  <h4 style={{ margin: "8px 0" }}>Files</h4>
                  {files.map((f) => (
                    <FileCard key={f.path} f={f} />
                  ))}
                </div>
              )}
            </>
          )}

          {result && (
            <pre
              style={{
                background: "#0b1020",
                color: "#e5e7eb",
                padding: 12,
                borderRadius: 8,
                maxHeight: 420,
                overflow: "auto",
              }}
            >
{pretty}
            </pre>
          )}
        </div>

        <div style={{ border: "1px solid #e5e7eb", padding: 16, borderRadius: 12 }}>
          <h3 style={{ marginTop: 0 }}>Recent</h3>
          <div style={{ display: "grid", gap: 8 }}>
            {recent.map((it) => (
              <div
                key={it.id}
                style={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr auto",
                  alignItems: "center",
                  gap: 8,
                  padding: 8,
                  border: "1px solid #eee",
                  borderRadius: 8,
                }}
              >
                <code style={{ opacity: 0.7 }}>#{it.id}</code>
                <div>
                  <div style={{ fontWeight: 600 }}>{it.task}</div>
                  <div style={{ fontSize: 12, opacity: 0.8 }}>
                    {JSON.stringify(it.payload)}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Badge status={it.status} />
                  <button
                    onClick={() => {
                      setJobId(String(it.id));
                      setResult(null);
                      setWatching(true);
                      autoPoll(String(it.id));
                    }}
                  >
                    Watch
                  </button>
                </div>
              </div>
            ))}
            {recent.length === 0 && (
              <div style={{ opacity: 0.7 }}>No recent items</div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
