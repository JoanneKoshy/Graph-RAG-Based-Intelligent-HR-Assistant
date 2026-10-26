// Page 3 - one employee: HR database facts on the left, knowledge-graph insights on the right.
import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { Bar, Card, DataTable, ErrorBox, PageHeader, Spinner } from "../components/ui.jsx";
import GraphView from "../components/GraphView.jsx";

export default function PeoplePage({ empId, setEmpId, askAbout }) {
  const [people, setPeople] = useState([]);
  const [filter, setFilter] = useState("");
  const [p, setP] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.employees()
      .then((list) => {
        setPeople(list);
        if (!empId && list.length) setEmpId(list[0].emp_id);
      })
      .catch((e) => setError(e.message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!empId) return;
    setP(null);
    setError(null);
    api.employee(empId).then(setP).catch((e) => setError(e.message));
  }, [empId]);

  const shown = useMemo(() => {
    const f = filter.toLowerCase();
    return people.filter((x) => (x.employee_name + " " + x.department).toLowerCase().includes(f));
  }, [people, filter]);

  const o = p && p.overview;
  return (
    <div>
      <PageHeader title="Employee profile"
        subtitle="Everything we know about one person: HR database facts, plus what the knowledge graph learned from reviews, project reports and resumes." />

      <div className="picker">
        <input placeholder="Filter by name or department..." value={filter} onChange={(e) => setFilter(e.target.value)} />
        <select value={empId || ""} onChange={(e) => setEmpId(Number(e.target.value))}>
          {shown.map((x) => (
            <option key={x.emp_id} value={x.emp_id}>
              {x.employee_name} - {x.department}{x.status !== "Active" ? " (" + x.status + ")" : ""}
            </option>
          ))}
        </select>
      </div>

      <ErrorBox message={error} />
      {!p && !error && <Spinner label="Loading profile..." />}
      {o && (
        <>
          <div className="profile-head card">
            <div className="avatar-lg">{o.employee_name.split(" ").map((w) => w[0]).join("").slice(0, 2)}</div>
            <div className="profile-main">
              <h2>{o.employee_name}</h2>
              <div className="muted">
                {o.designation} &middot; {o.department} &middot; {o.location} &middot; reports to {o.manager_name || "-"}
              </div>
              <div className="muted small">
                Employee ID {o.emp_id} &middot; {o.experience_years} years of experience &middot; {o.status}
              </div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Latest rating</div>
              <div className="kpi-value">{o.latest_rating ?? "-"}<span className="muted small"> / 5</span></div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Attendance</div>
              <div className="kpi-value">{o.attendance_pct ?? "-"}<span className="muted small"> %</span></div>
            </div>
          </div>

          <div className="grid-2">
            <div>
              <Card title="Performance reviews"><DataTable rows={p.reviews} /></Card>
              <Card title="Skills" note="proficiency 1-5">
                <DataTable rows={p.skills} render={{ proficiency: (v) => <Bar value={v} max={5} /> }} />
              </Card>
              <Card title="Projects"><DataTable rows={p.projects} /></Card>
            </div>
            <div>
              <Card title="Insights from documents" note="knowledge graph">
                <ErrorBox message={p.graph_error && "Could not reach Neo4j: " + p.graph_error} />
                {p.insights.length === 0 && !p.graph_error && (
                  <p className="muted small">No document-based facts about this person yet.</p>
                )}
                <dl className="facts">
                  {p.insights.map((i) => (
                    <div key={i.label} className="fact-row">
                      <dt>{i.label}</dt>
                      <dd>{i.values.join(", ")}</dd>
                    </div>
                  ))}
                </dl>
              </Card>
              <Card title="Ask the assistant about this person">
                <div className="stack">
                  <button className="sample" onClick={() => askAbout("Is " + o.employee_name + " eligible for promotion under our appraisal policy?")}>
                    Is {o.employee_name} eligible for promotion under our appraisal policy?
                  </button>
                  <button className="sample" onClick={() => askAbout("Who does " + o.employee_name + " mentor or collaborate with, and how are they performing?")}>
                    Who does {o.employee_name} mentor or collaborate with, and how are they performing?
                  </button>
                </div>
              </Card>
            </div>
          </div>

          {p.graph && (
            <Card title={o.employee_name + " in the knowledge graph"}>
              <GraphView nodes={p.graph.nodes} edges={p.graph.edges} center={p.graph.center} height={460} />
            </Card>
          )}
        </>
      )}
    </div>
  );
}
