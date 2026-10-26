// Interactive network drawing (vis-network). Solid edge = HR database fact, dashed = extracted from documents.
import { useEffect, useRef } from "react";
import { Network } from "vis-network/standalone";
import { LABEL_COLORS, DEFAULT_COLOR } from "./ui.jsx";

// Two nodes can be linked by several relationships (e.g. ASSIGNED_TO and CONTRIBUTED_TO).
// Draw them as one line with a combined label so the labels do not overlap.
function mergeEdges(edges) {
  const byPair = new Map();
  for (const e of edges) {
    const key = e.source + "|" + e.target;
    const m = byPair.get(key) || { from: e.source, to: e.target, rels: [], allExtracted: true };
    const name = e.rel.toLowerCase().replace(/_/g, " ");
    if (!m.rels.includes(name)) m.rels.push(name);
    m.allExtracted = m.allExtracted && !!e.extracted;
    byPair.set(key, m);
  }
  return [...byPair.values()].map((m, i) => ({
    id: i, from: m.from, to: m.to, label: m.rels.join(", "),
    title: m.rels.join(", ") + (m.allExtracted ? " (from documents)" : " (from database)"),
    dashes: m.allExtracted,
  }));
}

export default function GraphView({ nodes, edges, center, height = 480, onNodeClick, legend = true }) {
  const box = useRef(null);
  const clickRef = useRef(onNodeClick);
  clickRef.current = onNodeClick;

  useEffect(() => {
    if (!box.current) return;
    const data = {
      nodes: nodes.map((n) => ({
        id: n.id,
        label: n.name.length > 28 ? n.name.slice(0, 27) + "..." : n.name,
        title: n.label + ": " + n.name,
        color: { background: LABEL_COLORS[n.label] || DEFAULT_COLOR, border: "#ffffff",
                 highlight: { background: LABEL_COLORS[n.label] || DEFAULT_COLOR, border: "#0f172a" } },
        size: n.id === center ? 26 : 14,
        borderWidth: n.id === center ? 3 : 1,
      })),
      edges: mergeEdges(edges),
    };
    const network = new Network(box.current, data, {
      nodes: { shape: "dot", font: { size: 13, color: "#1e293b", face: "Inter, system-ui, sans-serif" } },
      edges: {
        arrows: { to: { enabled: true, scaleFactor: 0.5 } },
        color: { color: "#cbd5e1", highlight: "#64748b" },
        font: { size: 10, color: "#64748b", strokeWidth: 0 },
        smooth: { type: "continuous" },
      },
      physics: { barnesHut: { gravitationalConstant: -6000, springLength: 140 }, stabilization: { iterations: 150 } },
      interaction: { hover: true },
    });
    network.on("click", (p) => {
      if (p.nodes.length && clickRef.current) {
        const n = nodes.find((x) => x.id === p.nodes[0]);
        if (n) clickRef.current(n);
      }
    });
    network.once("stabilizationIterationsDone", () => network.fit());
    return () => network.destroy();
  }, [nodes, edges, center]);

  const labels = [...new Set(nodes.map((n) => n.label))].filter((l) => LABEL_COLORS[l]).sort();
  return (
    <div>
      <div ref={box} className="graph-box" style={{ height }} />
      {legend && labels.length > 0 && (
        <div className="legend">
          {labels.map((l) => (
            <span key={l}><i style={{ background: LABEL_COLORS[l] }} />{l}</span>
          ))}
          <span className="muted">solid line = database, dashed = from documents</span>
        </div>
      )}
    </div>
  );
}
