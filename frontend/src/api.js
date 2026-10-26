// All calls to the Python API (src/api.py). Vite forwards /api to http://127.0.0.1:8000.
async function request(path, options) {
  let res;
  try {
    res = await fetch("/api" + path, options);
  } catch (e) {
    throw new Error("Cannot reach the API. Is  uvicorn src.api:app --port 8000  running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.status + " " + res.statusText);
  return data;
}

export const api = {
  demoQuestions: () => request("/demo-questions"),
  ask: (question) =>
    request("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }),
  dashboard: () => request("/dashboard"),
  employees: () => request("/employees"),
  employee: (id) => request("/employees/" + id),
  graphSearch: (q) => request("/graph/search?q=" + encodeURIComponent(q)),
  neighbours: (id, limit) => request("/graph/neighbours?id=" + encodeURIComponent(id) + "&limit=" + limit),
  graphStats: () => request("/graph/stats"),
};
