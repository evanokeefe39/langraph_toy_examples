import ChatWindow from "@/components/AIChatbot";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-24">
      <ChatWindow />
    </main>
  );
}
