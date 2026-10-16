import { Video } from "lucide-react";
import { notFound } from "next/navigation";

import { AppShell } from "@/components/shell/app-shell";
import { Button } from "@/components/ui/button";
import { Chip, EmptyState, PageHeader, Panel, PanelHeader, StatTile, Swatch } from "@/components/ui/display";
import type { Me } from "@/lib/api";
import { t } from "@/lib/i18n";

/**
 * Design review page for the app shell and components, with sample data and
 * no sign-in. Development only: returns 404 in production builds.
 */
const SAMPLE_ME: Me = {
  user_id: "00000000-0000-0000-0000-000000000001",
  email: "surgeon@hospital.example",
  second_factor: false,
  profile: {
    id: "00000000-0000-0000-0000-000000000001",
    full_name: "Sample Surgeon",
    title: "Consultant",
    specialty: "General surgery",
    locale: "en",
    created_at: "2026-10-16T00:00:00Z",
    updated_at: "2026-10-16T00:00:00Z",
  },
  workspaces: [
    { id: "w1", kind: "personal", name: "Personal", team_id: null, storage_quota_gb: 20 },
    { id: "w2", kind: "team", name: "HPB unit", team_id: "t1", storage_quota_gb: 200 },
  ],
  teams: [{ team_id: "t1", team_name: "HPB unit", org_id: "o1", role: "surgeon" }],
  organizations: [{ org_id: "o1", org_name: "Sample Hospital", role: "member" }],
  platform_admin: true,
};

const PHASES = [
  ["Preparation", "#8C8C84"],
  ["Calot's Triangle Dissection", "#2F6B4F"],
  ["Clipping and Cutting", "#B5532E"],
  ["Gallbladder Dissection", "#C9A227"],
  ["Gallbladder Packaging", "#6D5BA8"],
  ["Cleaning and Coagulation", "#3E8E8A"],
  ["Gallbladder Retraction", "#A64D79"],
] as const;

export default function DevShellPage() {
  if (process.env.NODE_ENV === "production") notFound();

  return (
    <AppShell me={SAMPLE_ME} fallback={{ email: SAMPLE_ME.email, fullName: "" }} apiError={null}>
      <PageHeader title="Component review" description="Sample data. This page exists only in development." />
      <div className="flex flex-col gap-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <StatTile label="Duration" value="24:59" />
          <StatTile label="Mean confidence" value="92.5" unit="%" />
          <StatTile label="Bleeding episodes" value="19" tone="danger" />
          <StatTile label="Smoke time" value="03:12" />
          <StatTile label="Idle time" value="00:17" hint="2 periods, longest 9 s" />
        </div>

        <Panel>
          <PanelHeader title="Status chips" />
          <div className="flex flex-wrap gap-2 p-5">
            <Chip>{t("status.uploading")}</Chip>
            <Chip>{t("status.processing")}</Chip>
            <Chip tone="accent">{t("status.ready")}</Chip>
            <Chip tone="accent">{t("status.analyzing")}</Chip>
            <Chip tone="accent">{t("status.analyzed")}</Chip>
            <Chip tone="warning">Low confidence</Chip>
            <Chip tone="danger">{t("status.failed")}</Chip>
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Buttons" />
          <div className="flex flex-wrap items-center gap-2 p-5">
            <Button>Analyze video</Button>
            <Button variant="secondary">Download report</Button>
            <Button variant="ghost">Cancel</Button>
            <Button variant="danger">Delete video</Button>
            <Button loading>Saving</Button>
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Phase colors" description="Fixed data colors, identical in player, charts, and reports." />
          <div className="p-5">
            <div className="flex h-6 w-full overflow-hidden rounded-control" aria-hidden>
              {PHASES.map(([name, color], i) => (
                <div key={name} style={{ backgroundColor: color, flex: [3, 9, 2, 6, 2, 3, 1][i] }} />
              ))}
            </div>
            <ul className="mt-4 grid gap-1.5 sm:grid-cols-2">
              {PHASES.map(([name, color]) => (
                <li key={name}>
                  <Swatch color={color} label={name} />
                </li>
              ))}
            </ul>
          </div>
        </Panel>

        <EmptyState icon={Video} title={t("library.emptyTitle")} body={t("library.emptyBody")} action={<Button>{t("library.upload")}</Button>} />
      </div>
    </AppShell>
  );
}
