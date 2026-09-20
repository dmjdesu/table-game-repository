import MysteryBuilder from "../../../components/MysteryBuilder";

export default async function MysteryPage({ params }: { params: Promise<{ gameId: string }> }) {
  const { gameId } = await params;
  return <main className="shell"><h1>マーダーミステリー</h1><MysteryBuilder initialGameId={gameId} /></main>;
}
