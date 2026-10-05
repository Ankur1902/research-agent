"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Check,
  Clock3,
  Download,
  ExternalLink,
  ShieldCheck,
  Workflow,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Research, Source, Trace } from "@/lib/types";
import { Badge, ErrorMessage } from "./ui";
import { EvidenceDialog } from "./evidence-dialog";
export function ResearchWorkspace({
  id,
  tab = "report",
}: {
  id: string;
  tab?: string;
}) {
  const client = useQueryClient();
  const [selected, setSelected] = useState<Source | null>(null);
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: job, error } = useQuery({
    queryKey: ["research", id],
    queryFn: () => api<Research>(`/research/${id}`),
  });
  const { data: sources = [] } = useQuery({
    queryKey: ["sources", id],
    queryFn: () => api<Source[]>(`/research/${id}/sources`),
  });
  const { data: events = [] } = useQuery({
    queryKey: ["trace", id],
    queryFn: () => api<Trace[]>(`/research/${id}/trace`),
  });
  useEffect(() => {
    if (
      !job ||
      [
        "WAITING_FOR_APPROVAL",
        "REVIEW",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
      ].includes(job.status)
    )
      return;
    const stream = new EventSource(`/api/v1/research/${id}/events`);
    stream.onmessage = (event) => {
      const value = JSON.parse(event.data) as Trace;
      client.setQueryData<Trace[]>(["trace", id], (old) =>
        old?.some((e) => e.id === value.id) ? old : [...(old || []), value],
      );
      if (value.type === "source_found")
        client.invalidateQueries({ queryKey: ["sources", id] });
    };
    stream.addEventListener("checkpoint", () => {
      stream.close();
      client.invalidateQueries({ queryKey: ["research", id] });
      client.invalidateQueries({ queryKey: ["sources", id] });
    });
    return () => stream.close();
  }, [id, job, client]);
  async function action(name: string) {
    setBusy(true);
    setActionError("");
    try {
      await api(`/research/${id}/${name}`, { method: "POST" });
      await client.invalidateQueries({ queryKey: ["research", id] });
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (error) return <ErrorMessage error={error} />;
  if (!job) return <div className="skeleton" />;
  return (
    <>
      <div className="workspace-heading">
        <Link href="/dashboard" className="back-link">
          ← Back to overview
        </Link>
        <div>
          <span className="eyebrow">RESEARCH WORKSPACE · {job.mode}</span>
          <Badge>{job.status}</Badge>
        </div>
        <h1>{job.question}</h1>
        <div className="workspace-meta">
          <span>
            <Clock3 size={15} />
            {job.depth} research
          </span>
          <span>
            <BookOpen size={15} />
            {sources.length} sources
          </span>
          <span>
            Estimated spend ${job.cost.toFixed(4)} / ${job.budget.toFixed(2)}
          </span>
        </div>
      </div>
      {job.mode === "DEMO" && (
        <div className="demo-notice">
          DEMO — local fixture only. This is not evidence about your research
          topic.
        </div>
      )}
      {(job.error || actionError) && (
        <div role="alert" className="error-box">
          {job.error || actionError}
        </div>
      )}
      <nav className="tabs">
        {["report", "trace", "sources"].map((name) => (
          <Link
            className={tab === name ? "selected" : ""}
            href={`/research/${id}/${name}`}
            key={name}
          >
            {name === "report"
              ? "Research & report"
              : name === "trace"
                ? "Agent activity"
                : "Evidence library"}
          </Link>
        ))}
      </nav>
      {["WAITING_FOR_APPROVAL", "REVIEW"].includes(job.status) && (
        <div className="approval-bar">
          <div>
            <ShieldCheck size={22} />
            <span>
              <b>
                {job.status === "REVIEW"
                  ? "Review the report before finalizing"
                  : "Your plan is ready for review"}
              </b>
              <small>
                {job.status === "REVIEW"
                  ? "Inspect claims, evidence and limitations before approval."
                  : `Approving permits ${job.source_mode} access within your $${job.budget.toFixed(2)} budget.`}
              </small>
            </span>
          </div>
          <button
            disabled={busy}
            className="button"
            onClick={() => action("approve")}
          >
            <Check size={16} />
            {job.status === "REVIEW" ? "Approve report" : "Approve & research"}
          </button>
        </div>
      )}
      <div className="research-panels">
        <aside className="panel plan-panel">
          <h3>
            <Workflow size={18} />
            Research plan
          </h3>
          {job.plan ? (
            <ol>
              {job.plan.tasks.map((task) => (
                <li key={task.id}>
                  <b>{task.question}</b>
                  <small>{task.agent.replaceAll("_", " ")}</small>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">The manager is preparing a structured plan.</p>
          )}
          <div className="plan-divider" />
          <h3>Execution activity</h3>
          <div className="mini-trace" aria-live="polite">
            {events.slice(-8).map((event) => (
              <div key={event.id}>
                <span
                  className={`trace-dot ${event.type.includes("failed") ? "failed" : ""}`}
                />
                <span>
                  <b>{event.agent.replaceAll("_", " ")}</b>
                  <small>{event.message}</small>
                </span>
              </div>
            ))}
          </div>
          {!["COMPLETED", "CANCELLED", "FAILED"].includes(job.status) && (
            <button
              className="cancel-button"
              disabled={busy}
              onClick={() => action("cancel")}
            >
              <X size={14} />
              Cancel research
            </button>
          )}
        </aside>
        <section className="panel report-panel">
          {tab === "trace" ? (
            <>
              <span className="eyebrow">SAFE OPERATIONAL TRACE</span>
              <h2>From plan to evidence</h2>
              <p className="muted">
                Actions, tools and results. No private model reasoning.
              </p>
              {events.map((event) => (
                <details className="trace-detail" key={event.id}>
                  <summary>
                    <Badge>{event.type}</Badge>
                    <b>{event.agent}</b>
                    <span>
                      {new Date(event.created_at).toLocaleTimeString()}
                    </span>
                  </summary>
                  <p>{event.message}</p>
                  <pre>{JSON.stringify(event.details, null, 2)}</pre>
                </details>
              ))}
            </>
          ) : tab === "sources" ? (
            <>
              <span className="eyebrow">EVIDENCE LIBRARY</span>
              <h2>{sources.length} inspectable sources</h2>
              {sources.map((source) => (
                <button
                  className="source-expanded"
                  key={source.id}
                  onClick={() => setSelected(source)}
                >
                  <span className="citation-tag">[{source.citation}]</span>
                  <h3>{source.title}</h3>
                  <small>{source.domain}</small>
                  <p>{source.evidence.slice(0, 280)}…</p>
                </button>
              ))}
            </>
          ) : job.report ? (
            <>
              <div className="report-top">
                <span className="eyebrow">
                  {job.status === "COMPLETED"
                    ? "APPROVED REPORT"
                    : "RESEARCH DRAFT"}
                </span>
                <div className="export-links">
                  {["markdown", "html", "json", "pdf"].map((format) => (
                    <a
                      key={format}
                      href={`/api/v1/research/${id}/export?format=${format}`}
                    >
                      <Download size={13} />
                      {format.toUpperCase()}
                    </a>
                  ))}
                </div>
              </div>
              <h2>{job.report.title}</h2>
              <p className="report-summary">{job.report.summary}</p>
              {job.report.sections.map((section, index) => (
                <section className="report-section" key={index}>
                  <span className="section-number">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <h3>{section.title}</h3>
                  {section.finding_indices.map((i) => {
                    const finding = job.report!.findings[i];
                    return (
                      <article className="finding" key={i}>
                        <div>
                          <span className="finding-kind">{finding.kind}</span>
                          <Badge>{finding.status}</Badge>
                        </div>
                        <p>
                          {finding.text}{" "}
                          {finding.citations.map((key) => (
                            <button
                              className="citation-link"
                              onClick={() =>
                                setSelected(
                                  sources.find((s) => s.citation === key) ||
                                    null,
                                )
                              }
                              key={key}
                            >
                              [{key}]
                            </button>
                          ))}
                        </p>
                      </article>
                    );
                  })}
                </section>
              ))}
              <section className="limitations">
                <h3>Limitations & uncertainty</h3>
                <ul>
                  {job.report.limitations.map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </section>
            </>
          ) : (
            <div className="awaiting">
              <Workflow size={38} />
              <h2>
                {job.status === "WAITING_FOR_APPROVAL"
                  ? "A clear plan. Your call."
                  : job.status === "FAILED"
                    ? "Research needs attention."
                    : "Research is taking shape."}
              </h2>
              <p>
                {job.status === "WAITING_FOR_APPROVAL"
                  ? "Review the plan on the left, then approve to start gathering evidence."
                  : "Agent progress and sources appear here as work proceeds."}
              </p>
              <div className="pipeline-steps">
                {["Plan", "Research", "Verify", "Report"].map((name, i) => (
                  <span key={name}>
                    <b>{i + 1}</b>
                    {name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
        <aside className="panel evidence-panel">
          <h3>
            <BookOpen size={17} />
            Sources <span>{sources.length}</span>
          </h3>
          {sources.length ? (
            sources.map((source) => (
              <button
                className="source-card"
                key={source.id}
                onClick={() => setSelected(source)}
              >
                <span className="citation-tag">[{source.citation}]</span>
                <b>{source.title}</b>
                <small>{source.domain}</small>
                <span className="inspect-link">
                  Inspect evidence <ExternalLink size={12} />
                </span>
              </button>
            ))
          ) : (
            <p className="muted">
              Evidence will appear after the plan is approved.
            </p>
          )}
          <div className="evidence-note">
            <ShieldCheck size={18} />
            <p>
              A citation links to stored evidence. Inspect the passage and
              verification status before relying on a claim.
            </p>
          </div>
        </aside>
      </div>
      {selected && (
        <EvidenceDialog source={selected} onClose={() => setSelected(null)} />
      )}
    </>
  );
}
