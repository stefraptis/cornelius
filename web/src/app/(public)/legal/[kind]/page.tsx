import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { LEGAL_KINDS, LEGAL_TITLES, type LegalKind, renderLegal } from "@/lib/legal";
import { cn } from "@/lib/utils";

type Params = Promise<{ kind: string }>;

export function generateStaticParams() {
  return LEGAL_KINDS.map((kind) => ({ kind }));
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { kind } = await params;
  return { title: LEGAL_TITLES[kind as LegalKind] ?? "Legal" };
}

export default async function LegalPage({ params }: { params: Params }) {
  const { kind } = await params;
  if (!LEGAL_KINDS.includes(kind as LegalKind)) notFound();
  const html = await renderLegal(kind as LegalKind);

  return (
    <>
      <nav className="mb-8 flex flex-wrap gap-1 border-b border-border" aria-label="Legal documents">
        {LEGAL_KINDS.map((k) => (
          <Link
            key={k}
            href={`/legal/${k}`}
            aria-current={k === kind ? "page" : undefined}
            className={cn(
              "-mb-px border-b-2 border-transparent px-3 py-2 text-sm text-text-muted hover:text-text",
              k === kind && "border-accent text-text",
            )}
          >
            {LEGAL_TITLES[k]}
          </Link>
        ))}
      </nav>
      <article className="legal" dangerouslySetInnerHTML={{ __html: html }} />
    </>
  );
}
