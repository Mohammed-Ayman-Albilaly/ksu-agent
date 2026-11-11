import type { Metadata } from "next";
import { ChatScreen } from "@/components/chat/ChatScreen";
import { dictionary } from "@/lib/i18n";

export const metadata: Metadata = {
  title: dictionary.ar.chat.metaTitle,
};

export default function ChatPage() {
  return <ChatScreen />;
}
