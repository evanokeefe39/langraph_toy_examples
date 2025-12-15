'use client';
import {
    Conversation,
    ConversationContent,
    ConversationScrollButton,
} from '@/components/ui/shadcn-io/ai/conversation';
import { Loader } from '@/components/ui/shadcn-io/ai/loader';
import { Message, MessageAvatar, MessageContent } from '@/components/ui/shadcn-io/ai/message';
import {
    PromptInput,
    PromptInputButton,
    PromptInputModelSelect,
    PromptInputModelSelectContent,
    PromptInputModelSelectItem,
    PromptInputModelSelectTrigger,
    PromptInputModelSelectValue,
    PromptInputSubmit,
    PromptInputTextarea,
    PromptInputToolbar,
    PromptInputTools,
} from '@/components/ui/shadcn-io/ai/prompt-input';
import {
    Reasoning,
    ReasoningContent,
    ReasoningTrigger,
} from '@/components/ui/shadcn-io/ai/reasoning';
import { Source, Sources, SourcesContent, SourcesTrigger } from '@/components/ui/shadcn-io/ai/source';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { MicIcon, PaperclipIcon, RotateCcwIcon } from 'lucide-react';
import { nanoid } from 'nanoid';
import { type ChangeEvent, type FormEventHandler, useCallback, useEffect, useState } from 'react';
type ChatMessage = {
    id: string;
    content: string;
    role: 'user' | 'assistant';
    timestamp: Date;
    reasoning?: string;
    sources?: Array<{ title: string; url: string }>;
    isStreaming?: boolean;
};
const models = [
    { id: 'gpt-4o', name: 'GPT-4o' },
    { id: 'claude-3-5-sonnet', name: 'Claude 3.5 Sonnet' },
    { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro' },
    { id: 'llama-3.1-70b', name: 'Llama 3.1 70B' },
];

const ChatWindow = () => {
    const [messages, setMessages] = useState<ChatMessage[]>([
        {
            id: nanoid(),
            content: "Hello! I'm your AI assistant. I can help you with coding questions, explain concepts, and provide guidance on web development topics. What would you like to know?",
            role: 'assistant',
            timestamp: new Date(),
            sources: [
                { title: "Getting Started Guide", url: "#" },
                { title: "API Documentation", url: "#" }
            ]
        }
    ]);

    const [inputValue, setInputValue] = useState('');
    const [selectedModel, setSelectedModel] = useState(models[0].id);
    const [isTyping, setIsTyping] = useState(false);
    const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);

    const handleSubmit: FormEventHandler<HTMLFormElement> = useCallback(async (event) => {
        event.preventDefault();

        if (!inputValue.trim() || isTyping) return;

        const userMessageId = nanoid();
        const userMessage: ChatMessage = {
            id: userMessageId,
            content: inputValue.trim(),
            role: 'user',
            timestamp: new Date(),
        };

        setMessages(prev => [...prev, userMessage]);
        setInputValue('');
        setIsTyping(true);

        const assistantMessageId = nanoid();
        const assistantMessage: ChatMessage = {
            id: assistantMessageId,
            content: '',
            role: 'assistant',
            timestamp: new Date(),
            isStreaming: true,
            reasoning: '', // Start with empty reasoning but visible
        };
        setMessages(prev => [...prev, assistantMessage]);
        setStreamingMessageId(assistantMessageId);

        try {
            const response = await fetch('http://localhost:8000/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    messages: [{ role: 'user', content: userMessage.content }],
                    id: 'session-1',
                }),
            });

            if (!response.body) throw new Error('No response body');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || ''; // Keep the last partial line in the buffer

                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const data = JSON.parse(line);

                        setMessages(prev => prev.map(msg => {
                            if (msg.id === assistantMessageId) {
                                let updates: Partial<ChatMessage> = {};

                                if (data.type === 'reasoning_chunk') {
                                    updates.reasoning = (msg.reasoning || '') + data.text;
                                } else if (data.type === 'content_chunk') {
                                    updates.content = (msg.content || '') + data.text;
                                } else if (data.type === 'sources') {
                                    updates.sources = data.data;
                                } else if (data.type === 'done') {
                                    updates.isStreaming = false;
                                }

                                return { ...msg, ...updates };
                            }
                            return msg;
                        }));

                        if (data.type === 'done') {
                            setIsTyping(false);
                            setStreamingMessageId(null);
                        }

                    } catch (e) {
                        console.error('Error parsing line:', line, e);
                    }
                }
            }
        } catch (error) {
            console.error('Fetch error:', error);
            setIsTyping(false);
            setStreamingMessageId(null);
        }
    }, [inputValue, isTyping]);
    const handleReset = useCallback(() => {
        setMessages([
            {
                id: nanoid(),
                content: "Hello! I'm your AI assistant. I can help you with coding questions, explain concepts, and provide guidance on web development topics. What would you like to know?",
                role: 'assistant',
                timestamp: new Date(),
                sources: [
                    { title: "Getting Started Guide", url: "#" },
                    { title: "API Documentation", url: "#" }
                ]
            }
        ]);
        setInputValue('');
        setIsTyping(false);
        setStreamingMessageId(null);
    }, []);
    return (
        <div className="flex h-full w-full flex-col overflow-hidden rounded-xl border bg-background shadow-sm">
            {/* Header */}
            <div className="flex items-center justify-between border-b bg-muted/50 px-4 py-3">
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                        <div className="size-2 rounded-full bg-green-500" />
                        <span className="font-medium text-sm">AI Assistant</span>
                    </div>
                    <div className="h-4 w-px bg-border" />
                    <span className="text-muted-foreground text-xs">
                        {models.find(m => m.id === selectedModel)?.name}
                    </span>
                </div>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleReset}
                    className="h-8 px-2"
                >
                    <RotateCcwIcon className="size-4" />
                    <span className="ml-1">Reset</span>
                </Button>
            </div>
            {/* Conversation Area */}
            <Conversation className="flex-1">
                <ConversationContent className="space-y-4">
                    {messages.map((message) => (
                        <div key={message.id} className="space-y-3">
                            <Message from={message.role}>
                                <MessageContent>
                                    {message.isStreaming && message.content === '' ? (
                                        <div className="flex items-center gap-2">
                                            <Loader size={14} />
                                            <span className="text-muted-foreground text-sm">Thinking...</span>
                                        </div>
                                    ) : (
                                        message.content
                                    )}
                                </MessageContent>
                                <MessageAvatar
                                    src={message.role === 'user' ? 'https://github.com/dovazencot.png' : 'https://github.com/vercel.png'}
                                    name={message.role === 'user' ? 'User' : 'AI'}
                                />
                            </Message>
                            {/* Reasoning */}
                            {(message.reasoning || message.isStreaming) && (
                                <div className="ml-10">
                                    <Reasoning isStreaming={message.isStreaming} defaultOpen={false}>
                                        <ReasoningTrigger />
                                        <ReasoningContent>{message.reasoning || ''}</ReasoningContent>
                                    </Reasoning>
                                </div>
                            )}
                            {/* Sources */}
                            {message.sources && message.sources.length > 0 && (
                                <div className="ml-10">
                                    <Sources>
                                        <SourcesTrigger count={message.sources.length} />
                                        <SourcesContent>
                                            {message.sources.map((source, index) => (
                                                <Source key={index} href={source.url} title={source.title} />
                                            ))}
                                        </SourcesContent>
                                    </Sources>
                                </div>
                            )}
                        </div>
                    ))}
                </ConversationContent>
                <ConversationScrollButton />
            </Conversation>
            {/* Input Area */}
            <div className="border-t p-4">
                <PromptInput onSubmit={handleSubmit}>
                    <PromptInputTextarea
                        value={inputValue}
                        onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setInputValue(e.target.value)}
                        placeholder="Ask me anything about development, coding, or technology..."
                        disabled={isTyping}
                    />
                    <PromptInputToolbar>
                        <PromptInputTools>
                            <PromptInputButton disabled={isTyping}>
                                <PaperclipIcon size={16} />
                            </PromptInputButton>
                            <PromptInputButton disabled={isTyping}>
                                <MicIcon size={16} />
                                <span>Voice</span>
                            </PromptInputButton>
                            <PromptInputModelSelect
                                value={selectedModel}
                                onValueChange={setSelectedModel}
                                disabled={isTyping}
                            >
                                <PromptInputModelSelectTrigger>
                                    <PromptInputModelSelectValue />
                                </PromptInputModelSelectTrigger>
                                <PromptInputModelSelectContent>
                                    {models.map((model) => (
                                        <PromptInputModelSelectItem key={model.id} value={model.id}>
                                            {model.name}
                                        </PromptInputModelSelectItem>
                                    ))}
                                </PromptInputModelSelectContent>
                            </PromptInputModelSelect>
                        </PromptInputTools>
                        <PromptInputSubmit
                            disabled={!inputValue.trim() || isTyping}
                            status={isTyping ? 'streaming' : 'ready'}
                        />
                    </PromptInputToolbar>
                </PromptInput>
            </div>
        </div>
    );
};
export default ChatWindow;