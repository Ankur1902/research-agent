"use client";
import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, Check, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { Settings as Data, User } from "@/lib/types";
import { PageHeading, ErrorMessage } from "./ui";
export function Settings({ tab = "organization" }: { tab?: string }) {
  const client = useQueryClient();
  const { data, error } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Data>("/settings"),
  });
  const { data: user } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/auth/me"),
  });
  const [failure, setFailure] = useState("");
  const [saved, setSaved] = useState(false);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      await api("/settings", {
        method: "PATCH",
        body: JSON.stringify({
          default_depth: form.get("depth"),
          monthly_budget: Number(form.get("budget")),
        }),
      });
      await client.invalidateQueries({ queryKey: ["settings"] });
      setSaved(true);
    } catch (e) {
      setFailure((e as Error).message);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="YOUR WORKSPACE, YOUR CONTROLS"
        title="A considered configuration."
        description="Manage research defaults, provider readiness, and security boundaries."
      />
      <ErrorMessage error={error} />
      <nav className="tabs">
        {["account", "organization", "models", "security"].map((name) => (
          <Link
            href={`/settings/${name}`}
            className={tab === name ? "selected" : ""}
            key={name}
          >
            {name[0].toUpperCase() + name.slice(1)}
          </Link>
        ))}
      </nav>
      <section className="panel settings-panel">
        {tab === "account" ? (
          <>
            <h2>Your account</h2>
            <p>{user?.name}</p>
            <p>{user?.email}</p>
            <small>Role: {user?.role}</small>
          </>
        ) : tab === "models" ? (
          <>
            <h2>Provider configuration</h2>
            <p>
              Credentials are configured in server environment variables and
              never returned to your browser.
            </p>
            <div className="config-row">
              <span>
                Generation · {data?.provider} / {data?.model}
              </span>
              <Status ready={!!data?.generation_configured} />
            </div>
            <div className="config-row">
              <span>Search · {data?.search_provider}</span>
              <Status ready={!!data?.search_configured} />
            </div>
            <div className="config-row">
              <span>OpenAI embeddings</span>
              <Status ready={!!data?.embedding_configured} />
            </div>
            <p className="note">
              Set the corresponding API keys in .env and restart the API and
              worker. Model prices are configurable estimates.
            </p>
          </>
        ) : tab === "security" ? (
          <>
            <h2>
              <ShieldCheck size={21} />
              Security controls
            </h2>
            {[
              "Argon2 password hashing",
              "HttpOnly cookie sessions with 7-day expiry",
              "Origin validation and CSRF tokens",
              "Server-side organization isolation and RBAC",
              "Guarded source access and redirect validation",
              "Allowlisted tools and bounded execution",
              "Untrusted evidence labeling and output schemas",
            ].map((item) => (
              <div className="config-row" key={item}>
                <span>{item}</span>
                <Check size={17} />
              </div>
            ))}
            <p className="note">
              Email verification, password recovery delivery, MFA, malware
              scanning and external security review remain deployment
              requirements.
            </p>
          </>
        ) : data ? (
          <form key={JSON.stringify(data.preferences)} onSubmit={submit}>
            <h2>{data.organization}</h2>
            <p>Defaults for your organization’s research.</p>
            <label>
              Default research depth
              <select
                name="depth"
                defaultValue={data.preferences.default_depth || "standard"}
              >
                <option value="quick">Quick</option>
                <option value="standard">Standard</option>
                <option value="deep">Deep</option>
              </select>
            </label>
            <label>
              Organization spending ceiling (USD)
              <input
                name="budget"
                type="number"
                min="1"
                max="10000"
                defaultValue={data.preferences.monthly_budget || 50}
              />
            </label>
            <p className="note">
              The current ceiling applies to cumulative recorded research cost.
              Billing-period resets are not enabled.
            </p>
            {failure && (
              <p className="error" role="alert">
                {failure}
              </p>
            )}
            {saved && <p role="status">Settings saved.</p>}
            <button
              className="button"
              disabled={!["OWNER", "ADMIN"].includes(data.role)}
            >
              Save preferences
            </button>
          </form>
        ) : (
          <div className="skeleton" />
        )}
      </section>
    </>
  );
}
function Status({ ready }: { ready: boolean }) {
  return (
    <span className={ready ? "ready" : "error"}>
      {ready ? <Check size={15} /> : <AlertCircle size={15} />}{" "}
      {ready ? "Configured" : "Needs configuration"}
    </span>
  );
}
