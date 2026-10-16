import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Chip, PageHeader, Panel, PanelHeader, StatTile, Swatch } from "@/components/ui/display";
import { api, type Procedure } from "@/lib/api";
import { t } from "@/lib/i18n";
import { getAccessToken } from "@/lib/supabase/server";

export const metadata: Metadata = { title: t("aboutModel.title") };

type Metric = { mean: number; std: number; unit: string };

function metric(metrics: Record<string, unknown>, key: string): Metric | null {
  const value = metrics[key];
  if (value && typeof value === "object" && "mean" in value) return value as Metric;
  return null;
}

function ProcedureCard({ procedure }: { procedure: Procedure }) {
  const mv = procedure.model_version;
  const phaseAcc = mv ? metric(mv.metrics, "phase_balanced_accuracy") : null;
  const toolMap = mv ? metric(mv.metrics, "tool_map") : null;

  return (
    <Panel>
      <PanelHeader
        title={procedure.name}
        description={procedure.modality}
        actions={
          procedure.analysis_enabled ? (
            <Chip tone="accent">{t("aboutModel.analysisAvailable")}</Chip>
          ) : (
            <Chip>{t("aboutModel.comingSoon")}</Chip>
          )
        }
      />
      {mv ? (
        <div className="flex flex-col gap-6 p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            {phaseAcc ? (
              <StatTile
                label={t("aboutModel.phaseBalancedAccuracy")}
                value={`${phaseAcc.mean.toFixed(2)} ± ${phaseAcc.std.toFixed(2)}`}
                unit={phaseAcc.unit}
              />
            ) : null}
            {toolMap ? (
              <StatTile
                label={t("aboutModel.toolMap")}
                value={`${toolMap.mean.toFixed(2)} ± ${toolMap.std.toFixed(2)}`}
                unit={toolMap.unit}
              />
            ) : null}
          </div>
          <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[160px_1fr]">
            <dt className="text-text-muted">{t("aboutModel.dataset")}</dt>
            <dd>{String(mv.metrics.dataset ?? "")}</dd>
            <dt className="text-text-muted">{t("aboutModel.validation")}</dt>
            <dd>{String(mv.metrics.validation ?? "")}</dd>
            <dt className="text-text-muted">{t("aboutModel.architecture")}</dt>
            <dd>{mv.architecture}</dd>
          </dl>
          <div className="grid gap-6 sm:grid-cols-2">
            <div>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">
                {t("aboutModel.phases")} ({mv.phase_labels.length})
              </h3>
              <ol className="flex flex-col gap-1.5">
                {mv.phase_labels.map((p) => (
                  <li key={p.code}>
                    <Swatch color={p.color} label={p.name} />
                  </li>
                ))}
              </ol>
            </div>
            <div>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">
                {t("aboutModel.instruments")} ({mv.tool_labels.length})
              </h3>
              <ul className="flex flex-col gap-1.5">
                {mv.tool_labels.map((tool) => (
                  <li key={tool.code} className="flex items-baseline justify-between gap-2">
                    <Swatch color={tool.color} label={tool.name} />
                    {tool.name !== tool.code ? (
                      <span className="font-mono text-xs text-text-muted">{tool.code}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <p className="text-xs text-text-muted">{t("aboutModel.disclaimer")}</p>
        </div>
      ) : null}
    </Panel>
  );
}

export default async function AboutModelPage() {
  const token = await getAccessToken();
  if (!token) redirect("/login");
  const procedures = await api.procedures(token);
  const enabled = procedures.filter((p) => p.analysis_enabled);
  const comingSoon = procedures.filter((p) => !p.analysis_enabled);

  return (
    <>
      <PageHeader title={t("aboutModel.title")} description={t("aboutModel.intro")} />
      <div className="flex flex-col gap-6">
        {enabled.map((p) => (
          <ProcedureCard key={p.code} procedure={p} />
        ))}
        <Panel>
          <PanelHeader title={t("aboutModel.comingSoon")} />
          <ul className="divide-y divide-border">
            {comingSoon.map((p) => (
              <li key={p.code} className="flex items-center justify-between px-5 py-3 text-sm">
                <span>{p.name}</span>
                <span className="text-xs text-text-muted">{p.modality}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </>
  );
}
