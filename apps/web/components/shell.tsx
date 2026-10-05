"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  Layers3,
  LayoutDashboard,
  FolderOpen,
  BookOpen,
  FlaskConical,
  Settings2,
  ArrowUpRight,
  Plus,
  LogOut,
  Moon,
  Menu,
} from "lucide-react";
import { api, setCSRF } from "@/lib/api";
import type { User } from "@/lib/types";
const links = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/projects", label: "Projects", icon: FolderOpen },
  { href: "/documents", label: "Knowledge base", icon: BookOpen },
  { href: "/evaluations", label: "Evaluations", icon: FlaskConical },
];
export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(false);
  const { data: user, error } = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const value = await api<User>("/auth/me");
      setCSRF(value.csrf);
      return value;
    },
    retry: false,
  });
  useEffect(() => {
    if (error && error.message.includes("Sign in")) router.replace("/login");
  }, [error, router]);
  if (!user)
    return (
      <div className="loading-page">
        <Layers3 />
        <p>{error ? error.message : "Opening your workspace…"}</p>
        {error && <Link href="/login">Sign in</Link>}
      </div>
    );
  return (
    <div className={`app-shell ${dark ? "dark" : ""}`}>
      <button
        className="mobile-menu icon-button"
        aria-label="Toggle navigation"
        onClick={() => setOpen(!open)}
      >
        <Menu />
      </button>
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <Link className="brand" href="/dashboard">
          <Layers3 size={25} />
          Research<span>OS</span>
        </Link>
        <div className="workspace-switch">
          <span className="workspace-avatar">{user.name[0].toUpperCase()}</span>
          <div>
            <b>Research workspace</b>
            <small>{user.role.toLowerCase()} account</small>
          </div>
          <span>⌄</span>
        </div>
        <p className="nav-caption">WORKSPACE</p>
        <nav>
          {links.map(({ href, label, icon: Icon }) => (
            <Link
              onClick={() => setOpen(false)}
              className={path.startsWith(href) ? "active" : ""}
              key={href}
              href={href}
            >
              <Icon size={18} />
              {label}
            </Link>
          ))}
        </nav>
        <Link className="new-research-nav" href="/research/new">
          <Plus size={18} />
          New research <span>↗</span>
        </Link>
        <div className="sidebar-bottom">
          <div className="sidebar-tip">
            <span className="dot" />
            <b>Evidence over intuition.</b>
            <p>A clearer path from question to decision.</p>
            <Link href="/research/new">
              Start exploring <ArrowUpRight size={15} />
            </Link>
          </div>
          <Link className="settings-nav" href="/settings">
            <Settings2 size={18} />
            Settings
          </Link>
          <div className="user-row">
            <span className="avatar">{user.name[0]}</span>
            <div>
              <b>{user.name}</b>
              <small>{user.email}</small>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={async () => {
                await api("/auth/logout", { method: "POST" });
                router.push("/login");
              }}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span>Workspace</span>
            <span>/</span>
            <b>
              {path.startsWith("/research")
                ? "Research"
                : links.find((l) => path.startsWith(l.href))?.label ||
                  "Settings"}
            </b>
          </div>
          <div>
            <span className="system-status">
              <span className="dot" />
              ResearchOS
            </span>
            <button
              className="icon-button"
              aria-label="Toggle dark mode"
              onClick={() => setDark(!dark)}
            >
              <Moon size={17} />
            </button>
            <span className="avatar small">{user.name[0]}</span>
          </div>
        </header>
        <main className="content">{children}</main>
        <footer className="app-footer">
          ResearchOS <span>Every finding has a foundation.</span>
        </footer>
      </div>
    </div>
  );
}
