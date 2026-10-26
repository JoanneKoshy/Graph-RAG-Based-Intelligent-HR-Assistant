// Page 1 - chat with the full Graph RAG pipeline, and show how each answer was found.
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../api.js";
import { Badge, DataTable, ErrorBox, PageHeader } from "../components/ui.jsx";
import GraphView from "../components/GraphView.jsx";

const ROUTE_TONES = { sql: "blue", graph: "violet", documents: "orange" };
const STEPS = ["Understanding the question", "Searching the database, graph and documents", "Writing the answer"];

function Thinking() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const step = seconds < 4 ? 0 : seconds < 12 ? 1 : 2;
  return (
    <div className="msg msg-assistant">
      <div className="avatar">AI</div>
      <div className="bubble">
        {STEPS.map((s, i) => (
          <div key={s} className={"step " + (i < step ? "done" : i === step ? "now" : "")}>
            <span className="step-dot" /> {s}
          </div>
        ))}
        <div className="muted small">{seconds}s &middot; usually 10-30 seconds (longer if Groq asks us to wait)</div>
      </div>
    </div>
  );
}

function Badges({ r }) {
  const a = r.analysis;
  const g = r.grounding;
  const conf = { high: "green", medium: "orange", low: "red" }[r.confidence] || "gray";
  return (
    <div className="badges">
      {a.route.split("+").map((p) => (
        <Badge key={p} tone={ROUTE_TONES[p] || "gray"}>{p.toUpperCase()}</Badge>
      ))}
      <Badge tone={conf}>{r.confidence} confidence</Badge>
      {g && (
        <Badge tone={g.grounded_pct >= 90 ? "green" : g.grounded_pct >= 70 ? "orange" : "red"}>
          {g.grounded_pct}% grounded
        </Badge>
      )}
      <Badge>{r.total_seconds}s</Badge>
    </div>
  );
}

function Evidence({ r }) {
  const ctx = r.context;
  const a = r.analysis;
  const tabs = ["Understanding"];
  if (ctx.sql) tabs.push("SQL");
  if (ctx.graph) tabs.push("Knowledge graph");
  if (ctx.documents) tabs.push("Documents");
  tabs.push("Checks");
  const [tab, setTab] = useState(tabs[0]);

  return (
    <div className="evidence">
      <div className="tabs">
        {tabs.map((t) => (
          <button key={t} className={"tab" + (tab === t ? " active" : "")} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>

      {tab === "Understanding" && (
        <div>
          <dl className="facts">
            <dt>Intent</dt><dd>{a.intent}</dd>
            <dt>Route</dt><dd>{a.route}</dd>
            <dt>Rewritten question</dt><dd>{a.rewritten_question}</dd>
            {a.doc_classes && a.doc_classes.length > 0 && (<><dt>Document classes</dt><dd>{a.doc_classes.join(", ")}</dd></>)}
          </dl>
          {a.entities && a.entities.length > 0 && (
            <DataTable rows={a.entities.map((e) => ({
              mention: e.text, type: e.type,
              linked_to: e.match ? e.match.label + ": " + e.match.name : "-",
            }))} />
          )}
        </div>
      )}

      {tab === "SQL" && (
        <div>
          {ctx.sql.query && <pre className="code">{ctx.sql.query}</pre>}
          {ctx.sql.error ? <ErrorBox message={ctx.sql.error} /> : (
            <>
              <p className="muted small">{ctx.sql.row_count} row(s){ctx.sql.truncated ? " (only the first rows were sent to the LLM)" : ""}</p>
              <DataTable rows={ctx.sql.rows} />
            </>
          )}
        </div>
      )}

      {tab === "Knowledge graph" && (
        <div>
          {ctx.graph.query && <pre className="code">{ctx.graph.query}</pre>}
          {ctx.graph.error ? <ErrorBox message={ctx.graph.error} /> : (
            <>
              <p className="muted small">{ctx.graph.row_count} row(s) from the graph query</p>
              <DataTable rows={ctx.graph.rows} />
            </>
          )}
          {r.fact_graph && r.fact_graph.edges.length > 0 && (
            <>
              <h4>Related facts around the people and projects in the question</h4>
              <GraphView nodes={r.fact_graph.nodes} edges={r.fact_graph.edges} height={340} legend={false} />
              <p className="muted small">Solid line = HR database, dashed line = extracted from documents.</p>
            </>
          )}
          {ctx.graph.related_facts.length > 0 && <DataTable rows={ctx.graph.related_facts} maxHeight={240} />}
        </div>
      )}

      {tab === "Documents" && (
        <div className="docs">
          {ctx.documents.map((d, i) => (
            <div key={i} className="doc">
              <div><strong>{d.doc_id}</strong> <Badge>{d.type || "document"}</Badge></div>
              <p className="muted small">{d.text}</p>
            </div>
          ))}
        </div>
      )}

      {tab === "Checks" && (
        <div>
          {r.grounding && (
            <p>
              <strong>Grounding check:</strong> {r.grounding.grounded_pct}% of {r.grounding.checked} numbers and
              names in the answer were found in the retrieved data.
            </p>
          )}
          {r.grounding && r.grounding.unsupported.length > 0 && (
            <ErrorBox message={"Not found in the retrieved data: " + r.grounding.unsupported.join(", ")} />
          )}
          <h4>Time per step (seconds)</h4>
          <DataTable rows={[r.timings]} />
          <p className="muted small">LLM calls for this answer: {r.llm_calls}</p>
        </div>
      )}
    </div>
  );
}

function Answer({ r, onFollowUp, busy }) {
  const [open, setOpen] = useState(false);
  const hasContext = r.context && Object.keys(r.context).length > 0;
  return (
    <div className="msg msg-assistant">
      <div className="avatar">AI</div>
      <div className="bubble">
        <div className="answer"><ReactMarkdown>{r.answer}</ReactMarkdown></div>
        {hasContext && <Badges r={r} />}
        {r.follow_up_questions.length > 0 && (
          <div className="followups">
            {r.follow_up_questions.map((q) => (
              <button key={q} className="chip" disabled={busy} onClick={() => onFollowUp(q)}>{q}</button>
            ))}
          </div>
        )}
        {hasContext && (
          <>
            <button className="link-btn" onClick={() => setOpen(!open)}>
              {open ? "Hide" : "Show"} how this answer was found
            </button>
            {open && <Evidence r={r} />}
          </>
        )}
      </div>
    </div>
  );
}

export default function AskPage({ chat, setChat, pending, clearPending }) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [samples, setSamples] = useState([]);
  const [usage, setUsage] = useState(null);
  const endRef = useRef(null);

  useEffect(() => {
    api.demoQuestions().then(setSamples).catch(() => {});
  }, []);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat, busy]);

  const send = async (question) => {
    const q = (question || "").trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setChat((c) => [...c, { role: "user", text: q }]);
    try {
      const r = await api.ask(q);
      setUsage(r.usage);
      setChat((c) => [...c, { role: "assistant", result: r }]);
    } catch (e) {
      setChat((c) => [...c, { role: "error", text: e.message }]);
    } finally {
      setBusy(false);
    }
  };

  const sentRef = useRef(null); // stops React's development double-run from sending the same question twice
  useEffect(() => {
    if (!pending) {
      sentRef.current = null;
    } else if (sentRef.current !== pending && !busy) {
      sentRef.current = pending;
      clearPending();
      send(pending);
    }
  }, [pending]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="chat-page">
      <PageHeader title="Ask the HR assistant"
        subtitle="Plain-English questions, answered from the HR database, the knowledge graph and HR documents, with sources.">
        {usage && <span className="muted small">Groq this session: {usage.calls} calls, {usage.tokens.toLocaleString()} tokens</span>}
        {chat.length > 0 && <button className="btn" disabled={busy} onClick={() => setChat([])}>Clear chat</button>}
      </PageHeader>

      <div className="chat-scroll">
        {chat.length === 0 && (
          <div className="welcome card">
            <h3>Hi! What would you like to know?</h3>
            <p className="muted">
              Ask about employees, departments, projects, attendance, payroll, performance, candidates,
              mentoring, soft skills or HR policies. Try one of these:
            </p>
            <div className="samples">
              {samples.map((q) => (
                <button key={q} className="sample" onClick={() => send(q)}>{q}</button>
              ))}
            </div>
          </div>
        )}

        {chat.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="msg msg-user"><div className="bubble">{m.text}</div></div>
          ) : m.role === "error" ? (
            <div key={i} className="msg msg-assistant">
              <div className="avatar">AI</div>
              <div className="bubble"><ErrorBox message={m.text} /></div>
            </div>
          ) : (
            <Answer key={i} r={m.result} onFollowUp={send} busy={busy} />
          )
        )}
        {busy && <Thinking />}
        <div ref={endRef} />
      </div>

      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <textarea
          value={input}
          rows={1}
          placeholder="Ask about employees, projects, policies..."
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
          }}
        />
        <button className="btn btn-primary" type="submit" disabled={busy || !input.trim()}>Send</button>
      </form>
    </div>
  );
}
