import { Settings } from "@/components/settings";
export default async function Page({
  params,
}: {
  params: Promise<{ tab?: string[] }>;
}) {
  const { tab } = await params;
  return <Settings tab={tab?.[0]} />;
}
