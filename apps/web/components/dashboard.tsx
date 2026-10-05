"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Plus,
  FolderOpen,
  Activity,
  FileCheck2,
  BookOpen,
  ArrowRight,
  Workflow,
  ShieldCheck,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Dashboard as Data } from "@/lib/types";
import { PageHeading, ErrorMessage, ResearchList } from "./ui";
export function Dashboard() {
  const { data, error, isPending } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<Data>("/dashboard"),
  });
  return (
    <>
      <PageHeading
        eyebrow="YOUR INTELLIGENCE HUB"
        title="A clearer view of what matters."
        description="Turn open questions into evidence-backed decisions."
        action={
          <Link href="/research/new" className="button">
            <Plus size={17} />
            New research
          </Link>
        }
      />
      <ErrorMessage error={error} />
      <section className="welcome-banner">
        <div>
          <span className="eyebrow">FROM QUESTION TO CONFIDENCE</span>
          <h2>
            Your next insight
            <br />
            starts with a good question.
          </h2>
          <p>
            Put a team of specialized agents to work.
            <br />
            Plan, investigate, verify — all in one workspace.
          </p>
          <Link href="/research/new">
            Explore a research question <ArrowRight size={17} />
          </Link>
        </div>
        <div className="orbital">
          <div className="orbit o1" />
          <div className="orbit o2" />
          <div className="orbit o3" />
          <span className="orbit-center">
            <Workflow size={42} />
          </span>
          <span className="orbit-node n1">
            <BookOpen size={23} />
          </span>
          <span className="orbit-node n2">
            <ShieldCheck size={23} />
          </span>
          <span className="orbit-node n3">
            <Activity size={23} />
          </span>
          <span className="orbit-label">CONNECTED INTELLIGENCE</span>
        </div>
      </section>
      <div className="stats-grid">
        {[
          {
            label: "Research projects",
            value: data?.projects,
            icon: FolderOpen,
            sub: "Organized workspaces",
          },
          {
            label: "Active research",
            value: data?.active,
            icon: Activity,
            sub: "Agents at work",
          },
          {
            label: "Completed reports",
            value: data?.reports,
            icon: FileCheck2,
            sub: "Reviewed and approved",
          },
          {
            label: "Documents indexed",
            value: data?.documents,
            icon: BookOpen,
            sub: "Knowledge ready to retrieve",
          },
        ].map(({ label, value, icon: Icon, sub }) => (
          <article className="stat-card" key={label}>
            <div>
              <span>{label}</span>
              <Icon size={18} />
            </div>
            <strong>{isPending ? "—" : (value ?? 0)}</strong>
            <small>{sub}</small>
          </article>
        ))}
      </div>
      <div className="dashboard-grid">
        <section className="panel recent-panel">
          <div className="panel-heading">
            <h2>Recent research</h2>
            <Link href="/projects">
              View projects <ArrowUpRight size={15} />
            </Link>
          </div>
          <ResearchList jobs={data?.recent || []} />
        </section>
        <section className="panel activity-panel">
          <div className="panel-heading">
            <h2>Research activity</h2>
            <span className="muted">Actual job volume</span>
          </div>
          {data && Object.keys(data.volume).length ? (
            <div className="bar-chart">
              {Object.entries(data.volume)
                .slice(-7)
                .map(([day, count]) => (
                  <div key={day}>
                    <span>{count}</span>
                    <div
                      className="bar"
                      style={{
                        height: `${Math.max(8, (count / Math.max(...Object.values(data.volume))) * 110)}px`,
                      }}
                    />
                    <small>{day.slice(5)}</small>
                  </div>
                ))}
            </div>
          ) : (
            <div className="chart-empty">
              <Activity size={28} />
              <p>Activity appears when you run research.</p>
            </div>
          )}
          <div className="usage-row">
            <div>
              <small>Estimated AI & search cost</small>
              <b>${(data?.cost || 0).toFixed(4)}</b>
            </div>
            <div>
              <small>Avg. time to approval</small>
              <b>
                {data?.average_duration
                  ? `${Math.round(data.average_duration)}s`
                  : "—"}
              </b>
            </div>
          </div>
        </section>
      </div>
      <div className="section-label">
        <h2>Built for a stronger research process</h2>
        <span>HUMAN JUDGMENT. MACHINE ASSISTANCE.</span>
      </div>
      <div className="feature-grid">
        {[
          {
            icon: Workflow,
            title: "Watch the work happen",
            body: "Follow agents, tools, and evidence through the research lifecycle.",
            href: "/research/new",
            link: "Start a research job",
          },
          {
            icon: BookOpen,
            title: "Make knowledge useful",
            body: "Upload documents and retrieve the passages that answer your question.",
            href: "/documents",
            link: "Open knowledge base",
          },
          {
            icon: ShieldCheck,
            title: "Measure the foundation",
            body: "Evaluate citation mapping and evidence coverage using actual reports.",
            href: "/evaluations",
            link: "Explore evaluations",
          },
        ].map(({ icon: Icon, title, body, href, link }) => (
          <article className="feature-card" key={title}>
            <span className="feature-icon">
              <Icon size={21} />
            </span>
            <h3>{title}</h3>
            <p>{body}</p>
            <Link href={href}>
              {link}
              <ArrowUpRight size={15} />
            </Link>
          </article>
        ))}
      </div>
    </>
  );
}
