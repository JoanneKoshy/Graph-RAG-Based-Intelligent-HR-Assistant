// Page 2 - live workforce figures straight from the HR database (no LLM, so no Groq quota used).
import { useEffect, useState } from "react";
import {
  Bar as RBar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api.js";
import { Bar, Card, DataTable, ErrorBox, PageHeader, Spinner } from "../components/ui.jsx";

const BLUE = "#2563eb";

function Kpi({ label, value }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value ?? "-"}</div>
    </div>
  );
}

function HBar({ data, x, y, domain, ticks }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 30)}>
      <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20 }}>
        <CartesianGrid horizontal={false} stroke="#e2e8f0" />
        <XAxis type="number" domain={domain} ticks={ticks} tick={{ fontSize: 12 }} />
        <YAxis type="category" dataKey={y} width={130} tick={{ fontSize: 12 }} />
        <Tooltip />
        <RBar dataKey={x} fill={BLUE} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function VBar({ data, x, y }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ right: 10 }}>
        <CartesianGrid vertical={false} stroke="#e2e8f0" />
        <XAxis dataKey={x} tick={{ fontSize: 12 }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
        <Tooltip />
        <RBar dataKey={y} fill={BLUE} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function Trend({ data, x, y, domain }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ right: 20 }}>
        <CartesianGrid vertical={false} stroke="#e2e8f0" />
        <XAxis dataKey={x} tick={{ fontSize: 12 }} />
        <YAxis domain={domain} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Line type="monotone" dataKey={y} stroke={BLUE} strokeWidth={2} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export default function DashboardPage({ openProfile }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.dashboard().then(setD).catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <PageHeader title="Workforce dashboard" subtitle="Live figures from the HR database. Read-only, and no LLM involved." />
      <ErrorBox message={error} />
      {!d && !error && <Spinner label="Loading figures..." />}
      {d && (
        <>
          <div className="kpis">
            <Kpi label="Active employees" value={d.kpis.active_employees} />
            <Kpi label="Departments" value={d.kpis.departments} />
            <Kpi label="Ongoing projects" value={d.kpis.ongoing_projects} />
            <Kpi label="Avg rating (latest cycle)" value={d.kpis.avg_rating} />
            <Kpi label="Open candidates" value={d.kpis.open_candidates} />
          </div>

          <div className="grid-2">
            <Card title="Headcount by department" note="active employees">
              <HBar data={d.headcount} x="employees" y="department" />
            </Card>
            <Card title="Average rating by department" note="latest review cycle, out of 5">
              <HBar data={d.ratings} x="avg_rating" y="department" domain={[0, 5]} ticks={[0, 1, 2, 3, 4, 5]} />
            </Card>
            <Card title="Total monthly payroll" note="INR lakh">
              <Trend data={d.payroll} x="month" y="payroll_lakh" domain={[0, "auto"]} />
            </Card>
            <Card title="Attendance by month" note="% of working days present">
              <Trend data={d.attendance} x="month" y="attendance_pct" domain={[80, 100]} />
            </Card>
            <Card title="Candidate pipeline">
              <VBar data={d.candidates} x="status" y="candidates" />
            </Card>
            <Card title="Projects by status">
              <VBar data={d.projects} x="status" y="projects" />
            </Card>
          </div>

          <Card title="Employees to watch"
            note="Active employees with a latest rating below 2.5 or attendance below 85% over the last 3 months. A starting point for a conversation, not a verdict.">
            <DataTable
              rows={d.watch}
              columns={["employee_name", "department", "designation", "manager_name", "latest_rating", "attendance_3m"]}
              render={{
                employee_name: (v, r) => <button className="link-btn" onClick={() => openProfile(r.emp_id)}>{v}</button>,
                attendance_3m: (v) => <Bar value={v} max={100} />,
              }}
            />
          </Card>
        </>
      )}
    </div>
  );
}
