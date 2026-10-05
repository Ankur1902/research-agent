import { Evaluations } from "@/components/evaluations";
export default async function Page({
  params,
}: {
  params: Promise<{ id?: string[] }>;
}) {
  const { id } = await params;
  return <Evaluations id={id?.[0]} />;
}
