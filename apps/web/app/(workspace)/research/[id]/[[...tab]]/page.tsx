import { ResearchWorkspace } from "@/components/research-workspace";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string; tab?: string[] }>;
}) {
  const { id, tab } = await params;
  return <ResearchWorkspace id={id} tab={tab?.[0] || "report"} />;
}
