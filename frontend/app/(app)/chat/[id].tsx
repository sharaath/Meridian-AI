import React from 'react';
import { useLocalSearchParams } from 'expo-router';
import { ChatWorkspace } from '@/components/ChatWorkspace';

export default function ConversationPage() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <ChatWorkspace conversationId={id} />;
}

