"use client";
import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Plus, ArrowUpRight } from "lucide-react";
import { api } from "@/lib/api";
import type { Evaluation, Research } from "@/lib/types";
import { PageHeading, Badge, ErrorMessage, Empty } from "./ui";
export function Evaluations({ id }: { id?: string }) {
  const client = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [researchId, setResearchId] = useState("");
  const [topics, setTopics] = useState("");
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: runs = [], error } = useQuery({
    queryKey: ["evaluations"],
    queryFn: () => api<Evaluation[]>("/evaluations"),
  });
  const { data: jobs = [] } = useQuery({
    queryKey: ["researches"],
    queryFn: () => api<Research[]>("/research"),
  });
  const { data: run } = useQuery({
    queryKey: ["evaluation", id],
    queryFn: () => api<Evaluation>(`/evaluations/${id}`),
    enabled: !!id,
  });
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/evaluations", {
        method: "POST",
        body: JSON.stringify({
          name,
          research_id: researchId,
          expected_topics: topics
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean),
          expected_sources: [],
        }),
      });
      await client.invalidateQueries({ queryKey: ["evaluations"] });
      setCreating(false);
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="MAKE QUALITY MEASURABLE"
        title={
          id ? run?.name || "Evaluation" : "Evidence is only the beginning."
        }
        description="Measure citation mapping, topic coverage, and assessed claim support from actual reports."
        action={
          !id ? (
            <button className="button" onClick={() => setCreating(!creating)}>
              <Plus size={16} />
              Run evaluation
            </button>
          ) : undefined
        }
      />
      <ErrorMessage error={error} />
      {creating && (
        <form className="panel inline-form" onSubmit={submit}>
          <h2>Evaluate a report</h2>
          <label>
            Run name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            Research report
            <select
              required
              value={researchId}
              onChange={(e) => setResearchId(e.target.value)}
            >
              <option value="">Choose an existing report</option>
              {jobs
                .filter((j) => j.report)
                .map((j) => (
                  <option value={j.id} key={j.id}>
                    {j.question} ({j.mode})
                  </option>
                ))}
            </select>
          </label>
          <label>
            Expected topics (comma separated)
            <input
              value={topics}
              onChange={(e) => setTopics(e.target.value)}
              placeholder="market, risks, recommendations"
            />
          </label>
          {failure && (
            <p className="error" role="alert">
              {failure}
            </p>
          )}
          <button className="button" disabled={busy}>
            {busy ? "Evaluating…" : "Run evaluation"}
          </button>
        </form>
      )}
      {id && run ? (
        <section className="panel evaluation-result">
          <Badge>{run.results.mode}</Badge>
          <div className="metric-grid">
            {Object.entries(run.results.metrics).map(([key, value]) => (
              <div key={key}>
                <small>{key.replaceAll("_", " ")}</small>
                <strong>
                  {value === null
                    ? "Not measured"
                    : `${(value * 100).toFixed(1)}%`}
                </strong>
              </div>
            ))}
          </div>
          <p>{run.results.method}</p>
          <small>Estimated research cost: ${run.results.cost.toFixed(4)}</small>
        </section>
      ) : (
        <section className="panel">
          <div className="panel-heading">
            <h2>Evaluation history</h2>
            <span className="muted">Reproducible report checks</span>
          </div>
          {runs.length ? (
            runs.map((r) => (
              <Link
                className="research-row"
                href={`/evaluations/${r.id}`}
                key={r.id}
              >
                <FlaskConical size={21} />
                <div>
                  <b>{r.name}</b>
                  <small>{new Date(r.created_at).toLocaleString()}</small>
                </div>
                <Badge>{r.results.mode}</Badge>
                <ArrowUpRight size={17} />
              </Link>
            ))
          ) : (
            <Empty
              title="Measure before you trust"
              body="Generate a report, then run a reproducible evaluation. No scores are shown before a run."
            />
          )}
        </section>
      )}
    </>
  );
}
