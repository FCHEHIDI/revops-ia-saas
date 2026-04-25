"use client";

import { useRef, useState, type DragEvent, type ChangeEvent } from "react";
import { Upload, FileText, Trash2, CheckCircle, AlertCircle, Loader } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery, useApiMutation } from "@/hooks/useApi";
import { documentsApi } from "@/lib/api";
import { formatBytes, formatDate, cn } from "@/lib/utils";
import type { Document, DocumentStatus } from "@/types";

const statusConfig: Record<DocumentStatus, { label: string; variant: "success" | "info" | "warning" | "error" | "neutral"; icon: React.ElementType }> = {
  indexed: { label: "Indexé", variant: "success", icon: CheckCircle },
  processing: { label: "En cours", variant: "info", icon: Loader },
  uploading: { label: "Upload…", variant: "neutral", icon: Loader },
  error: { label: "Erreur", variant: "error", icon: AlertCircle },
};

export function DocumentsUpload() {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: documents, isLoading } = useApiQuery(
    ["documents"],
    () => documentsApi.listDocuments()
  );

  const uploadMutation = useApiMutation(
    (file: File) => documentsApi.uploadDocument(file),
    [["documents"]]
  );

  const deleteMutation = useApiMutation(
    (id: string) => documentsApi.deleteDocument(id),
    [["documents"]]
  );

  const handleFiles = (files: FileList | null) => {
    if (!files) return;
    Array.from(files).forEach((file) => uploadMutation.mutate(file));
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  return (
    <div className="space-y-6">
      {/* Upload zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={() => setIsDragging(false)}
        onClick={() => fileInputRef.current?.click()}
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-10 cursor-pointer transition-colors",
          isDragging
            ? "border-indigo-500 bg-indigo-500/10"
            : "border-slate-700 bg-slate-800/50 hover:border-slate-600 hover:bg-slate-800"
        )}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-500/10">
          <Upload className="h-6 w-6 text-indigo-400" />
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-slate-300">
            Glissez vos fichiers ici ou <span className="text-indigo-400">parcourez</span>
          </p>
          <p className="mt-1 text-xs text-slate-500">PDF, DOCX, TXT — max 50 MB</p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md"
          className="hidden"
          onChange={(e: ChangeEvent<HTMLInputElement>) => handleFiles(e.target.files)}
        />
      </div>

      {uploadMutation.isPending && (
        <div className="flex items-center gap-2 text-sm text-indigo-400">
          <Spinner size="sm" />
          Upload en cours…
        </div>
      )}

      {/* Documents list */}
      {isLoading ? (
        <div className="flex justify-center py-8">
          <Spinner size="lg" />
        </div>
      ) : (
        <div className="space-y-2">
          {(documents ?? []).map((doc: Document) => {
            const { label, variant, icon: Icon } = statusConfig[doc.status];
            return (
              <div
                key={doc.id}
                className="flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 hover:border-slate-600 transition-colors"
              >
                <FileText size={18} className="shrink-0 text-slate-500" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-200 truncate">{doc.filename}</p>
                  <p className="text-xs text-slate-500">
                    {formatBytes(doc.size)} · {formatDate(doc.uploaded_at)}
                    {doc.chunk_count && ` · ${doc.chunk_count} chunks`}
                  </p>
                </div>
                <Badge variant={variant} className="flex items-center gap-1 shrink-0">
                  <Icon size={10} className={doc.status === "processing" ? "animate-spin" : ""} />
                  {label}
                </Badge>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => deleteMutation.mutate(doc.id)}
                  disabled={deleteMutation.isPending}
                  className="shrink-0 text-slate-600 hover:text-red-400"
                >
                  <Trash2 size={14} />
                </Button>
              </div>
            );
          })}
          {(documents ?? []).length === 0 && (
            <p className="py-8 text-center text-sm text-slate-500">
              Aucun document indexé. Uploadez vos premiers fichiers ci-dessus.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
