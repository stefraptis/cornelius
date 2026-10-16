import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import type { SpriteIndex } from "@/components/player/video-player";
import { VideoPage } from "@/components/player/video-page";
import { ApiError, videosApi } from "@/lib/api";
import { getAccessToken } from "@/lib/supabase/server";

type Params = Promise<{ id: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { id } = await params;
  const token = await getAccessToken();
  if (!token) return {};
  try {
    const video = await videosApi.get(token, id);
    return { title: video.title };
  } catch {
    return {};
  }
}

export default async function VideoRoute({ params }: { params: Params }) {
  const { id } = await params;
  const token = await getAccessToken();
  if (!token) redirect("/login");
  let video;
  try {
    video = await videosApi.get(token, id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  let spriteUrl: string | null = null;
  let spriteIndex: SpriteIndex | null = null;
  if (["ready", "analyzing", "analyzed"].includes(video.status)) {
    try {
      const [sprite, index] = await Promise.all([
        videosApi.asset(token, id, "sprite"),
        videosApi.spriteIndex(token, id),
      ]);
      spriteUrl = sprite.url;
      spriteIndex = index;
    } catch {
      spriteUrl = null;
    }
  }
  return <VideoPage initial={video} spriteUrl={spriteUrl} spriteIndex={spriteIndex} />;
}
