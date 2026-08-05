import { ProjectDetailLive } from "@/components/dashboard/project-detail-live";

type ProjectDetailPageProps = {
  params: Promise<{ id: string }>;
};

export default async function ProjectDetailPage({ params }: ProjectDetailPageProps) {
  const { id } = await params;

  return <ProjectDetailLive projectId={id} />;
}
