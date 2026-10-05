"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowRight, Layers3 } from "lucide-react";
import { api, setCSRF } from "@/lib/api";
import type { User } from "@/lib/types";
const schema = z.object({
  email: z.string().email(),
  password: z.string().min(10).max(128),
  name: z.string().optional(),
  organization: z.string().optional(),
});
export function AuthForm({ registering = false }: { registering?: boolean }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });
  const submit = handleSubmit(async (data) => {
    setError("");
    try {
      const user = await api<User>(
        `/auth/${registering ? "register" : "login"}`,
        {
          method: "POST",
          body: JSON.stringify(
            registering ? data : { email: data.email, password: data.password },
          ),
        },
      );
      setCSRF(user.csrf);
      router.push("/dashboard");
    } catch (e) {
      setError((e as Error).message);
    }
  });
  return (
    <div className="auth-page">
      <aside>
        <Link href="/" className="brand">
          <Layers3 />
          Research<span>OS</span>
        </Link>
        <div>
          <span className="eyebrow">LESS NOISE. MORE EVIDENCE.</span>
          <h1>
            A better foundation
            <br />
            for your next decision.
          </h1>
          <p>
            One workspace. Specialized agents.
            <br />
            Research you can trace back to its sources.
          </p>
        </div>
        <small>RESEARCH · RETRIEVE · VERIFY · SYNTHESIZE</small>
      </aside>
      <main>
        <form onSubmit={submit}>
          <span className="eyebrow">YOUR RESEARCH WORKSPACE</span>
          <h2>{registering ? "Start with a question." : "Welcome back."}</h2>
          <p>
            {registering
              ? "Create an account and a private organization."
              : "Sign in to pick up where your research left off."}
          </p>
          {registering && (
            <>
              <label>
                Your name
                <input {...register("name")} required autoComplete="name" />
              </label>
              <label>
                Organization
                <input {...register("organization")} required />
              </label>
            </>
          )}
          <label>
            Email address
            <input {...register("email")} type="email" autoComplete="email" />
          </label>
          {errors.email && (
            <small className="error">Enter a valid email.</small>
          )}
          <label>
            Password
            <input
              {...register("password")}
              type="password"
              autoComplete={registering ? "new-password" : "current-password"}
            />
          </label>
          {errors.password && (
            <small className="error">Use at least 10 characters.</small>
          )}
          {error && (
            <div role="alert" className="error-box">
              {error}
            </div>
          )}
          <button className="button" disabled={isSubmitting}>
            {isSubmitting
              ? "Please wait…"
              : registering
                ? "Create workspace"
                : "Sign in"}
            <ArrowRight size={17} />
          </button>
          <p className="auth-switch">
            {registering ? "Already have an account?" : "New to ResearchOS?"}{" "}
            <Link href={registering ? "/login" : "/register"}>
              {registering ? "Sign in" : "Create an account"}
            </Link>
          </p>
        </form>
      </main>
    </div>
  );
}
