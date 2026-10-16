import type { Metadata } from "next";
import { Upload, Video } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState, PageHeader } from "@/components/ui/display";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/primitives";
import { t } from "@/lib/i18n";

export const metadata: Metadata = { title: t("library.title") };

export default function LibraryPage() {
  const uploadButton = (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0}>
          <Button disabled>
            <Upload aria-hidden /> {t("library.upload")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("library.uploadSoon")}</TooltipContent>
    </Tooltip>
  );

  return (
    <>
      <PageHeader title={t("library.title")} actions={uploadButton} />
      <Tabs defaultValue="mine">
        <TabsList>
          <TabsTrigger value="mine">{t("library.myVideos")}</TabsTrigger>
          <TabsTrigger value="shared">{t("library.sharedWithMe")}</TabsTrigger>
        </TabsList>
        <TabsContent value="mine">
          <EmptyState icon={Video} title={t("library.emptyTitle")} body={t("library.emptyBody")} action={uploadButton} />
        </TabsContent>
        <TabsContent value="shared">
          <EmptyState icon={Video} title={t("library.emptyTitle")} />
        </TabsContent>
      </Tabs>
    </>
  );
}
