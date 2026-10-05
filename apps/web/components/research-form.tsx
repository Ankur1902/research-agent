"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Sparkles,
  Clock3,
  Wallet,
  ShieldCheck,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Project, Research } from "@/lib/types";
import { PageHeading } from "./ui";
export function ResearchForm() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [depth, setDepth] = useState("standard");
  const [sources, setSources] = useState("both");
  const [mode, setMode] = useState("LIVE");
  const [project, setProject] = useState("");
  const [budget, setBudget] = useState(1);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const job = await api<Research>("/research", {
        method: "POST",
        body: JSON.stringify({
          question,
          depth,
          source_mode: sources,
          mode,
          budget,
          project_id: project || null,
        }),
      });
      router.push(`/research/${job.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="A NEW LINE OF INQUIRY"
        title="What would you like to understand?"
        description="A good question is the beginning. Your research team takes it from there."
      />
      <div className="form-layout">
        <form className="panel research-form" onSubmit={submit}>
          <div className="panel-heading">
            <h2>
              <Sparkles size={18} />
              Research brief
            </h2>
            <span className="badge">Human approval required</span>
          </div>
          <label>
            Research question
            <textarea
              autoFocus
              minLength={10}
              maxLength={4000}
              required
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Analyze the Indian EV market, compare company strategies, and identify growth drivers and risks…"
              rows={6}
            />
          </label>
          <small className="muted">
            Be specific about your scope, timeframe, and the decisions you want
            to inform.
          </small>
          <label>
            Project
            <select
              value={project}
              onChange={(e) => setProject(e.target.value)}
            >
              <option value="">Independent research</option>
              {projects?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>Research depth</legend>
            <div className="choice-grid">
              {[
                ["quick", "Quick", "A focused first look"],
                ["standard", "Standard", "A balanced investigation"],
                ["deep", "Deep", "A wider evidence base"],
              ].map(([value, title, body]) => (
                <button
                  key={value}
                  type="button"
                  className={`choice ${depth === value ? "selected" : ""}`}
                  onClick={() => setDepth(value)}
                  aria-pressed={depth === value}
                >
                  <b>{title}</b>
                  <small>{body}</small>
                </button>
              ))}
            </div>
          </fieldset>
          <div className="form-columns">
            <label>
              Evidence sources
              <select
                value={sources}
                onChange={(e) => setSources(e.target.value)}
              >
                <option value="both">Web + knowledge base</option>
                <option value="web">Web research</option>
                <option value="documents">Uploaded documents</option>
              </select>
            </label>
            <label>
              Execution mode
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="LIVE">
                  Live · provider credentials required
                </option>
                <option value="DEMO">Demo · labeled local fixture</option>
              </select>
            </label>
          </div>
          <label>
            Maximum estimated spend (USD)
            <input
              type="number"
              min="0.01"
              max="20"
              step="0.01"
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
            />
          </label>
          {error && (
            <div className="error-box" role="alert">
              {error}
            </div>
          )}
          <div className="form-footer">
            <span>
              <ShieldCheck size={16} />
              Review the plan before execution
            </span>
            <button className="button" disabled={busy}>
              {busy ? "Creating…" : "Generate research plan"}
              <ArrowRight size={16} />
            </button>
          </div>
        </form>
        <aside>
          <div className="panel estimate-card">
            <span className="eyebrow">BEFORE YOU BEGIN</span>
            <h3>A controlled investigation.</h3>
            <p>
              Your team will build a plan for you to review before collecting
              evidence.
            </p>
            <div>
              <Clock3 size={19} />
              <span>
                <b>{depth === "deep" ? "3–10 minutes" : "1–5 minutes"}</b>
                <small>Rough estimate; providers vary</small>
              </span>
            </div>
            <div>
              <Wallet size={19} />
              <span>
                <b>Up to ${budget.toFixed(2)}</b>
                <small>Your configured spending ceiling</small>
              </span>
            </div>
            <div>
              <Sparkles size={19} />
              <span>
                <b>4–8 stages</b>
                <small>Planning through verification</small>
              </span>
            </div>
            <p className="note">
              These are estimates, not guarantees. Live usage and timing appear
              in the execution trace.
            </p>
          </div>
          <div className="example-question">
            <span className="eyebrow">NEED A STARTING POINT?</span>
            <button
              onClick={() =>
                setQuestion(
                  "Analyze the current Indian electric vehicle market, compare major manufacturers and business models, identify growth drivers and risks, and provide evidence-backed recommendations.",
                )
              }
            >
              Explore the Indian EV market <ArrowUpRightIcon />
            </button>
            <button
              onClick={() =>
                setQuestion(
                  "Compare retrieval-augmented generation and long-context approaches for enterprise knowledge systems, including costs, security risks and evaluation methods.",
                )
              }
            >
              Compare enterprise AI approaches <ArrowUpRightIcon />
            </button>
          </div>
        </aside>
      </div>
    </>
  );
}
function ArrowUpRightIcon() {
  return <span aria-hidden="true">↗</span>;
}
