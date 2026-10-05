"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, UploadCloud, ArrowUpRight } from "lucide-react";
import { api } from "@/lib/api";
import type { Document } from "@/lib/types";
import { PageHeading, Badge, ErrorMessage, Empty } from "./ui";
export function Documents({ id }: { id?: string }) {
  const input = useRef<HTMLInputElement>(null);
  const client = useQueryClient();
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [failure, setFailure] = useState("");
  const { data: documents = [], error } = useQuery({
    queryKey: ["documents"],
    queryFn: () => api<Document[]>("/documents"),
    refetchInterval: (query) =>
      query.state.data?.some((d) => ["QUEUED", "PROCESSING"].includes(d.status))
        ? 3000
        : false,
  });
  const { data: document } = useQuery({
    queryKey: ["document", id],
    queryFn: () => api<Document>(`/documents/${id}`),
    enabled: !!id,
  });
  async function upload(file: File) {
    setFailure("");
    if (
      file.size > 10 * 1024 * 1024 ||
      !/\.(pdf|txt|md|csv)$/i.test(file.name)
    ) {
      setFailure("Choose a PDF, TXT, Markdown or CSV file under 10 MB.");
      return;
    }
    setUploading(true);
    setProgress(0);
    try {
      const user = await api<{ csrf: string }>("/auth/me");
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/v1/documents");
        xhr.setRequestHeader("X-CSRF-Token", user.csrf);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable)
            setProgress(Math.round((e.loaded / e.total) * 100));
        };
        xhr.onload = () => {
          if (xhr.status < 300) resolve();
          else {
            let message = "Upload failed";
            try {
              message = JSON.parse(xhr.responseText).detail;
            } catch {}
            reject(new Error(message));
          }
        };
        xhr.onerror = () => reject(new Error("Upload connection failed"));
        const form = new FormData();
        form.append("file", file);
        xhr.send(form);
      });
      await client.invalidateQueries({ queryKey: ["documents"] });
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setUploading(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="YOUR KNOWLEDGE, CONNECTED"
        title={
          id ? document?.name || "Document" : "Give your research a foundation."
        }
        description="Turn trusted documents into retrievable, citable evidence."
        action={
          !id ? (
            <button className="button" onClick={() => input.current?.click()}>
              <UploadCloud size={17} />
              Upload document
            </button>
          ) : undefined
        }
      />
      <ErrorMessage error={error} />
      {failure && (
        <div className="error-box" role="alert">
          {failure}
        </div>
      )}
      {id ? (
        <section className="panel document-detail">
          <Badge>{document?.status || "Loading"}</Badge>
          {document?.error && <p className="error">{document.error}</p>}
          <p>{document?.chunk_count} chunks · Page metadata preserved</p>
          <pre>{document?.text}</pre>
        </section>
      ) : (
        <>
          <input
            className="sr-only"
            type="file"
            ref={input}
            accept=".pdf,.txt,.md,.csv"
            aria-label="Choose document"
            onChange={(e) => {
              if (e.target.files?.[0]) upload(e.target.files[0]);
            }}
          />
          <button
            className="upload-zone"
            disabled={uploading}
            onClick={() => input.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
            }}
          >
            <span>
              <UploadCloud size={26} />
            </span>
            <h3>
              {uploading
                ? `Uploading · ${progress}%`
                : "Drop a document. Find a new perspective."}
            </h3>
            <p>Drag and drop, or click to browse</p>
            <small>PDF, TXT, Markdown, CSV · Up to 10 MB</small>
            {uploading && <progress max={100} value={progress} />}
          </button>
          <section className="panel">
            <div className="panel-heading">
              <h2>Document library</h2>
              <span className="muted">{documents.length} documents</span>
            </div>
            {documents.length ? (
              documents.map((doc) => (
                <div className="document-row" key={doc.id}>
                  <FileText size={20} />
                  <Link href={`/documents/${doc.id}`}>
                    <b>{doc.name}</b>
                    <small>
                      {doc.error ||
                        new Date(doc.created_at).toLocaleDateString()}
                    </small>
                  </Link>
                  <Badge>{doc.status}</Badge>
                  {doc.status === "FAILED" && (
                    <button
                      className="text-button"
                      onClick={async () => {
                        try {
                          await api(`/documents/${doc.id}/retry`, {
                            method: "POST",
                          });
                          await client.invalidateQueries({
                            queryKey: ["documents"],
                          });
                        } catch (e) {
                          setFailure((e as Error).message);
                        }
                      }}
                    >
                      Retry
                    </button>
                  )}
                  <ArrowUpRight size={17} />
                </div>
              ))
            ) : (
              <Empty
                title="Your knowledge base is ready for knowledge"
                body="Upload a document to parse, chunk, embed, and index it. Embedding credentials are required."
              />
            )}
          </section>
        </>
      )}
    </>
  );
}
