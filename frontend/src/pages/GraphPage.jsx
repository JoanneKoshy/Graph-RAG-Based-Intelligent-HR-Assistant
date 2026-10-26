// Page 4 - search the knowledge graph and walk through it. Click any node to explore it next.
import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Badge, Card, DataTable, ErrorBox, PageHeader, Spinner } from "../components/ui.jsx";
import GraphView from "../components/GraphView.jsx";

function Explorer() {
  const [text, setText] = useState("");
  const [hits, setHits] = useState(null);
  const [trail, setTrail] = useState([]); // nodes visited, last one is the focus
  const [limit, setLimit] = useState(50);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const [error, setError] = useState(null);
  const focus = trail[trail.length - 1];

  const search = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setError(null);
    try {
      const found = await api.graphSearch(text);
      setHits(found);
      if (found.length) setTrail([found[0]]);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    if (!focus) return;
    setLoading(true);
    setError(null);
    api.neighbours(focus.id, limit)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [focus, limit]);

  const goTo = (node) => {
    if (focus && node.id === focus.id) return;
    setTrail((t) => [...t, node]);
  };

  return (
    <div>
      <form className="search-row" onSubmit={search}>
        <input value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Search a person, project, skill, client, risk... e.g. Arya, Kafka, vendor" />
        <button className="btn btn-primary" type="submit">Search</button>
      </form>
      <ErrorBox message={error} />
      {hits && hits.length === 0 && <p className="muted">Nothing found. Try another spelling or a shorter word.</p>}
      {hits && hits.length > 0 && (
        <div className="followups">
          {hits.map((h) => (
            <button key={h.id} className={"chip" + (focus && focus.id === h.id ? " chip-active" : "")}
              onClick={() => setTrail([h])}>
              {h.name} <span className="muted small">({h.label})</span>
            </button>
          ))}
        </div>
      )}

      {focus && (
        <Card>
          <div className="graph-head">
            <div>
              <div className="trail">
                {trail.map((n, i) => (
                  <span key={n.id + i}>
                    {i > 0 && <span className="muted"> &rsaquo; </span>}
                    <button className="link-btn" onClick={() => setTrail(trail.slice(0, i + 1))}>{n.name}</button>
                  </span>
                ))}
              </div>
              <h2>{focus.name} <Badge>{focus.label}</Badge></h2>
            </div>
            <label className="muted small">
              Max connections{" "}
              <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
                {[20, 50, 100, 150].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
          </div>
          <p className="muted small">Click a node to explore it. Drag to move, scroll to zoom, hover for details.</p>
          {loading && <Spinner label="Loading connections..." />}
          {data && !loading && (
            data.nodes.length === 0 ? <p className="muted">This node has no connections.</p> : (
              <>
                <GraphView nodes={data.nodes} edges={data.edges} center={data.center} height={540} onNodeClick={goTo} />
                <button className="link-btn" onClick={() => setShowTable(!showTable)}>
                  {showTable ? "Hide" : "Show"} connections as a table ({data.table.length})
                </button>
                {showTable && <DataTable rows={data.table} />}
              </>
            )
          )}
        </Card>
      )}
      {!focus && !hits && <p className="muted">Search for something to see its connections.</p>}
    </div>
  );
}

function Stats() {
  const [s, setS] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    api.graphStats().then(setS).catch((e) => setError(e.message));
  }, []);
  if (error) return <ErrorBox message={error} />;
  if (!s) return <Spinner label="Counting..." />;
  return (
    <div className="grid-2">
      <Card title="Nodes by type"><DataTable rows={s.nodes} maxHeight={600} /></Card>
      <Card title="Relationships by type" note="from_documents = extracted by the LLM">
        <DataTable rows={s.relationships} maxHeight={600} />
      </Card>
    </div>
  );
}

export default function GraphPage() {
  const [tab, setTab] = useState("explore");
  return (
    <div>
      <PageHeader title="Knowledge graph explorer"
        subtitle="The graph behind Graph RAG: people, projects, skills and the relationships found in documents." />
      <div className="tabs">
        <button className={"tab" + (tab === "explore" ? " active" : "")} onClick={() => setTab("explore")}>Explore</button>
        <button className={"tab" + (tab === "stats" ? " active" : "")} onClick={() => setTab("stats")}>What is in the graph</button>
      </div>
      {tab === "explore" ? <Explorer /> : <Stats />}
    </div>
  );
}
