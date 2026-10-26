// Small shared building blocks: cards, badges, tables, spinner, error box.
export const LABEL_COLORS = {
  Employee: "#2563eb", Candidate: "#7c3aed", Department: "#0f766e", Project: "#ea580c",
  Skill: "#16a34a", SoftSkill: "#65a30d", Client: "#b45309", Training: "#0891b2",
  Outcome: "#db2777", Risk: "#dc2626", Company: "#475569", Institution: "#64748b",
};
export const DEFAULT_COLOR = "#94a3b8";

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </div>
  );
}

export function Card({ title, note, children, className = "" }) {
  return (
    <section className={"card " + className}>
      {title && (
        <h3 className="card-title">
          {title} {note && <span className="muted small">{note}</span>}
        </h3>
      )}
      {children}
    </section>
  );
}

export function Badge({ tone = "gray", children }) {
  return <span className={"badge badge-" + tone}>{children}</span>;
}

export function Spinner({ label }) {
  return (
    <div className="spinner-row">
      <span className="spinner" /> {label}
    </div>
  );
}

export function ErrorBox({ message }) {
  if (!message) return null;
  return <div className="error-box">{message}</div>;
}

function cell(v) {
  if (v === null || v === undefined) return "-";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function DataTable({ rows, columns, maxHeight = 360, render = {} }) {
  if (!rows || rows.length === 0) return <p className="muted small">No rows.</p>;
  const cols = columns || Object.keys(rows[0]);
  return (
    <div className="table-wrap" style={{ maxHeight }}>
      <table>
        <thead>
          <tr>{cols.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c} className={typeof r[c] === "number" ? "num" : ""}>
                  {render[c] ? render[c](r[c], r) : cell(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Bar({ value, max }) {
  const pct = Math.max(0, Math.min(100, (100 * (value || 0)) / max));
  return (
    <span className="bar-cell">
      <span className="bar-track"><span className="bar-fill" style={{ width: pct + "%" }} /></span>
      <span className="num">{value ?? "-"}</span>
    </span>
  );
}
