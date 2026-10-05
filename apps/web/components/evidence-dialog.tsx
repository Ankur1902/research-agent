"use client";
import { useEffect, useRef } from "react";
import { ExternalLink, X } from "lucide-react";
import type { Source } from "@/lib/types";

export function EvidenceDialog({
  source,
  onClose,
}: {
  source: Source;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="evidence-dialog"
      aria-label="Supporting evidence"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          const bounds = event.currentTarget.getBoundingClientRect();
          if (
            event.clientX < bounds.left ||
            event.clientX > bounds.right ||
            event.clientY < bounds.top ||
            event.clientY > bounds.bottom
          )
            onClose();
        }
      }}
    >
      <button
        autoFocus
        className="icon-button close-dialog"
        aria-label="Close evidence"
        onClick={onClose}
      >
        <X />
      </button>
      <span className="eyebrow">SUPPORTING EVIDENCE · [{source.citation}]</span>
      <h2>{source.title}</h2>
      {source.url.startsWith("http") ? (
        <a href={source.url} target="_blank" rel="noreferrer">
          Open original source <ExternalLink size={14} />
        </a>
      ) : (
        <small>{source.url}</small>
      )}
      <blockquote>{source.evidence}</blockquote>
      <small>
        Retrieved {new Date(source.created_at).toLocaleString()} ·{" "}
        {source.domain}
      </small>
    </dialog>
  );
}
