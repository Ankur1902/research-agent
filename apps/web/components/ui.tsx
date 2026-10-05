import Link from "next/link";
import { ArrowUpRight, Search, FileText } from "lucide-react";
import type { Research } from "@/lib/types";
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span
      className={`badge ${String(children).toLowerCase().replaceAll("_", "-")}`}
    >
      {String(children).replaceAll("_", " ")}
    </span>
  );
}
export function ErrorMessage({ error }: { error: Error | null }) {
  return error ? (
    <div className="error-box" role="alert">
      {error.message}
    </div>
  ) : null;
}
export function Empty({
  title,
  body,
  href,
  label,
}: {
  title: string;
  body: string;
  href?: string;
  label?: string;
}) {
  return (
    <div className="empty">
      <Search size={27} />
      <h3>{title}</h3>
      <p>{body}</p>
      {href && (
        <Link className="button secondary" href={href}>
          {label}
          <ArrowUpRight size={16} />
        </Link>
      )}
    </div>
  );
}
export function ResearchList({ jobs }: { jobs: Research[] }) {
  return jobs.length ? (
    <div className="research-list">
      {jobs.map((job) => (
        <Link
          className="research-row"
          href={`/research/${job.id}`}
          key={job.id}
        >
          <span className="row-icon">
            <FileText size={19} />
          </span>
          <div>
            <b>{job.question}</b>
            <small>
              {job.depth} depth <span>·</span>{" "}
              {new Date(job.created_at).toLocaleDateString("en-IN", {
                month: "short",
                day: "numeric",
              })}{" "}
              <span>·</span> {job.mode}
            </small>
          </div>
          <Badge>{job.status}</Badge>
          <span className="row-cost">${job.cost.toFixed(4)}</span>
          <ArrowUpRight size={17} />
        </Link>
      ))}
    </div>
  ) : (
    <Empty
      title="Your next discovery starts here"
      body="Create a research job to see its plan, evidence, and report in this workspace."
      href="/research/new"
      label="Start research"
    />
  );
}
