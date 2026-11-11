"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Layers } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { contentApi, messageFor, type ContentVersion } from "@/lib/contentApi";

const LETTERS = ["A", "B", "C", "D", "E", "F"];

// Read-only view of one stored version. Published versions are immutable, so
// nothing on this page is editable.
export default function AdminContentVersionPage() {
  const { question_id, version_no } = useParams<{ question_id: string; version_no: string }>();
  const [version, setVersion] = useState<ContentVersion | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const { data } = await contentApi.getVersion(question_id, Number(version_no));
      setVersion(data);
    } catch (err) {
      setLoadError(messageFor(err));
    }
  }, [question_id, version_no]);

  useEffect(() => {
    load();
  }, [load]);

  if (loadError) {
    return (
      <AdminLayout>
        <PageWrapper>
          <EmptyState icon={Layers} title="Could not load this version" subtitle={loadError} action={{ label: "Try again", onClick: load }} />
        </PageWrapper>
      </AdminLayout>
    );
  }

  return (
    <AdminLayout>
      <PageWrapper>
        <nav aria-label="Breadcrumb" className="text-xs mb-3" style={{ color: "var(--color-text-muted)" }}>
          <Link href="/admin/content" className="underline-offset-2 hover:underline">Content</Link>
          {" / "}
          <Link href={`/admin/content/questions/${question_id}`} className="underline-offset-2 hover:underline">Question</Link>
        </nav>

        {version === null ? (
          <Skeleton className="h-10 w-64" />
        ) : (
          <PageHeader
            title={`Version ${version.version_no}`}
            subtitle={`${version.state.replace("_", " ")} · read only`}
          />
        )}

        {version && (
          <article className="mt-6 space-y-5" aria-label="Version content">
            <div>
              <h2 className="text-xs font-medium mb-1" style={{ color: "var(--color-text-muted)" }}>Question</h2>
              <p className="break-words">{version.question_text}</p>
            </div>
            {version.explanation && (
              <div>
                <h2 className="text-xs font-medium mb-1" style={{ color: "var(--color-text-muted)" }}>Explanation</h2>
                <p className="break-words">{version.explanation}</p>
              </div>
            )}
            {version.image_url && (
              <div>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={version.image_url} alt={version.image_alt_text} className="max-h-60 rounded-[var(--radius-md)]" />
              </div>
            )}
            <div>
              <h2 className="text-xs font-medium mb-2" style={{ color: "var(--color-text-muted)" }}>Options</h2>
              <ul className="space-y-1">
                {version.options.map((o, idx) => (
                  <li key={idx} className="break-words">
                    {LETTERS[idx]}. {o.option_text}
                    {o.is_correct && <span className="ml-2 text-xs font-medium" style={{ color: "var(--color-text)" }}>(correct)</span>}
                  </li>
                ))}
              </ul>
            </div>
          </article>
        )}
      </PageWrapper>
    </AdminLayout>
  );
}
