import { Documents } from "@/components/documents";
export default async function Page({
  params,
}: {
  params: Promise<{ id?: string[] }>;
}) {
  const { id } = await params;
  return <Documents id={id?.[0]} />;
}
