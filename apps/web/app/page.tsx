import Link from "next/link";
import {
  ArrowRight,
  Layers3,
  ShieldCheck,
  Workflow,
  BookOpen,
  Check,
} from "lucide-react";
export default function Landing() {
  return (
    <div className="landing">
      <nav>
        <Link className="brand" href="/">
          <Layers3 size={25} />
          Research<span>OS</span>
        </Link>
        <div>
          <Link href="login">Sign in</Link>
          <Link className="button" href="register">
            Get started <ArrowRight size={16} />
          </Link>
        </div>
      </nav>
      <main className="hero">
        <span className="eyebrow">
          <span className="dot" /> YOUR RESEARCH, WITH A CLEARER SIGNAL
        </span>
        <h1>
          Research with an AI team.
          <br />
          <span>Make every finding count.</span>
        </h1>
        <p>
          From a complex question to a source-backed report. A shared workspace
          for research, evidence, and the decisions that follow.
        </p>
        <div className="hero-actions">
          <Link className="button" href="register">
            Create your workspace <ArrowRight size={17} />
          </Link>
          <Link className="button secondary" href="login">
            Explore the demo
          </Link>
        </div>
        <div className="hero-card">
          <div className="hero-card-top">
            <span className="eyebrow">THE RESEARCH PIPELINE</span>
            <span className="badge">Human control, built in</span>
          </div>
          <div className="pipeline">
            {["Plan", "Retrieve", "Analyze", "Verify", "Synthesize"].map(
              (name, i) => (
                <div key={name}>
                  <span className="pipeline-icon">
                    {i === 3 ? (
                      <ShieldCheck />
                    ) : i === 1 ? (
                      <BookOpen />
                    ) : (
                      <Workflow />
                    )}
                  </span>
                  <b>{name}</b>
                  <small>
                    {
                      [
                        "A structured plan",
                        "Real evidence",
                        "Bounded agents",
                        "Traceable claims",
                        "A useful report",
                      ][i]
                    }
                  </small>
                  {i < 4 && <ArrowRight className="pipeline-arrow" size={18} />}
                </div>
              ),
            )}
          </div>
        </div>
        <section className="landing-features">
          {[
            [
              "Evidence you can inspect",
              "Open a citation to see the exact supporting passage.",
            ],
            [
              "Approval before action",
              "Review the plan and budget before research begins.",
            ],
            [
              "Measured, not assumed",
              "Inspect execution traces, provider usage, and reproducible evaluations.",
            ],
          ].map(([title, body]) => (
            <article key={title}>
              <Check size={20} />
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </section>
        <p className="techline">NEXT.JS · FASTAPI · MYSQL · REDIS · QDRANT</p>
      </main>
      <footer>
        ResearchOS{" "}
        <span>
          Built for thoughtful research. Accuracy has limits; evidence makes
          them visible.
        </span>
      </footer>
    </div>
  );
}
