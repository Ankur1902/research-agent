"use client";
import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, Plus, ArrowUpRight } from "lucide-react";
import { api } from "@/lib/api";
import type { Project, Research } from "@/lib/types";
import { PageHeading, ErrorMessage, Empty, ResearchList } from "./ui";
export function Projects({ id }: { id?: string }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const { data: projects = [], error } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });
  const { data: project } = useQuery({
    queryKey: ["project", id],
    queryFn: () => api<Project>(`/projects/${id}`),
    enabled: !!id,
  });
  const { data: jobs = [] } = useQuery({
    queryKey: ["researches"],
    queryFn: () => api<Research[]>("/research"),
    enabled: !!id,
  });
  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/projects", {
        method: "POST",
        body: JSON.stringify({ name, description }),
      });
      setCreating(false);
      setName("");
      setDescription("");
      await client.invalidateQueries({ queryKey: ["projects"] });
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="ORGANIZE YOUR INQUIRY"
        title={
          id ? project?.name || "Project" : "A home for every big question."
        }
        description={
          id
            ? project?.description || "Research within this project."
            : "Keep related questions, reports, and decisions together."
        }
        action={
          id ? (
            <Link className="button" href="/research/new">
              <Plus size={16} />
              New research
            </Link>
          ) : (
            <button className="button" onClick={() => setCreating(!creating)}>
              <Plus size={16} />
              New project
            </button>
          )
        }
      />
      <ErrorMessage error={error} />
      {creating && (
        <form className="panel inline-form" onSubmit={create}>
          <h2>Create a project</h2>
          <label>
            Name
            <input
              required
              maxLength={200}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="India EV Market Intelligence"
            />
          </label>
          <label>
            Description
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </label>
          {failure && (
            <p role="alert" className="error">
              {failure}
            </p>
          )}
          <button className="button" disabled={busy}>
            {busy ? "Creating…" : "Create project"}
          </button>
        </form>
      )}
      {id ? (
        <section className="panel">
          <div className="panel-heading">
            <h2>Project research</h2>
          </div>
          <ResearchList jobs={jobs.filter((job) => job.project_id === id)} />
        </section>
      ) : projects.length ? (
        <div className="project-grid">
          {projects.map((p) => (
            <Link
              className="panel project-card"
              href={`/projects/${p.id}`}
              key={p.id}
            >
              <div>
                <FolderOpen size={25} />
                <ArrowUpRight size={19} />
              </div>
              <h2>{p.name}</h2>
              <p>
                {p.description || "A dedicated space for connected research."}
              </p>
              <small>
                Created {new Date(p.created_at).toLocaleDateString()}
              </small>
            </Link>
          ))}
        </div>
      ) : (
        <section className="panel">
          <Empty
            title="Make space for your research"
            body="Create your first project to organize questions and findings."
          />
        </section>
      )}
    </>
  );
}
