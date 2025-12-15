'use client';
import {
    Conversation,
    ConversationContent,
    ConversationScrollButton,
} from '@/components/ui/shadcn-io/ai/conversation';
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from '@/components/ui/collapsible';
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
import { Task, TaskTrigger, TaskContent, TaskItem, TaskItemFile } from '@/components/ui/shadcn-io/ai/task';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Tool, ToolHeader, ToolInput, ToolOutput, ToolContent } from '@/components/ui/shadcn-io/ai/tool';
import { MicIcon, PaperclipIcon, RotateCcwIcon, ChevronDownIcon } from 'lucide-react';
import { nanoid } from 'nanoid';
import { type ChangeEvent, type FormEventHandler, useCallback, useEffect, useState } from 'react';
import type { ToolUIPart } from 'ai';
type MessagePart =
    | { type: 'content'; content: string; id: string }
    | { type: 'reasoning'; content: string; id: string; isStreaming?: boolean }
    | { type: 'tool'; tool: ToolUIPart; id: string }
    | { type: 'task'; tasks: Array<{ title: string; items: string[] }>; id: string }
    | { type: 'source'; sources: Array<{ title: string; url: string }>; id: string }
    | { type: 'execution_log'; parts: MessagePart[]; id: string };

type ChatMessage = {
    id: string;
    role: 'user' | 'assistant';
    timestamp: Date;
    parts: MessagePart[];
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
            role: 'assistant',
            timestamp: new Date(),
            parts: [
                { type: 'content', content: "Hello! I'm your AI assistant. I can help you with coding questions, explain concepts, and provide guidance on web development topics. What would you like to know?", id: nanoid() },
                { type: 'source', sources: [{ title: "Getting Started Guide", url: "#" }, { title: "API Documentation", url: "#" }], id: nanoid() }
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
            role: 'user',
            timestamp: new Date(),
            parts: [{ type: 'content', content: inputValue.trim(), id: nanoid() }]
        };

        setMessages(prev => [...prev, userMessage]);
        setInputValue('');
        setIsTyping(true);

        const assistantMessageId = nanoid();
        const assistantMessage: ChatMessage = {
            id: assistantMessageId,
            role: 'assistant',
            timestamp: new Date(),
            parts: [],
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
                    messages: [{ role: 'user', content: inputValue.trim() }],
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
                                const newParts = [...msg.parts];
                                const lastPart = newParts[newParts.length - 1];
                                const hasPlan = newParts.some(p => p.type === 'task');

                                if (data.type === 'reasoning_chunk') {
                                    if (hasPlan) {
                                        // Add to Execution Log
                                        let executionLogIndex = newParts.findIndex(p => p.type === 'execution_log');
                                        if (executionLogIndex === -1) {
                                            newParts.push({ type: 'execution_log', parts: [], id: nanoid() });
                                            executionLogIndex = newParts.length - 1;
                                        }

                                        const logParts = [...(newParts[executionLogIndex] as any).parts];
                                        const lastLogPart = logParts[logParts.length - 1];

                                        if (lastLogPart && lastLogPart.type === 'reasoning') {
                                            logParts[logParts.length - 1] = { ...lastLogPart, content: lastLogPart.content + data.text };
                                        } else {
                                            logParts.push({ type: 'reasoning', content: data.text, id: nanoid(), isStreaming: true });
                                        }
                                        newParts[executionLogIndex] = { ...newParts[executionLogIndex], parts: logParts } as MessagePart;

                                    } else {
                                        // Initial Thinking
                                        if (lastPart && lastPart.type === 'reasoning') {
                                            newParts[newParts.length - 1] = { ...lastPart, content: lastPart.content + data.text };
                                        } else {
                                            newParts.push({ type: 'reasoning', content: data.text, id: nanoid(), isStreaming: true });
                                        }
                                    }
                                } else if (data.type === 'content_chunk') {
                                    if (lastPart && lastPart.type === 'content') {
                                        newParts[newParts.length - 1] = { ...lastPart, content: lastPart.content + data.text };
                                    } else {
                                        newParts.push({ type: 'content', content: data.text, id: nanoid() });
                                    }
                                } else if (data.type === 'sources') {
                                    newParts.push({ type: 'source', sources: data.data, id: nanoid() });
                                } else if (data.type === 'tasks') {
                                    const existingTaskIndex = newParts.findIndex(p => p.type === 'task');
                                    if (existingTaskIndex >= 0) {
                                        newParts[existingTaskIndex] = { ...newParts[existingTaskIndex], tasks: data.data } as MessagePart;
                                    } else {
                                        newParts.push({ type: 'task', tasks: data.data, id: nanoid() });
                                    }
                                } else if (data.type === 'tool_call') {
                                    const toolPartData = data.tool as ToolUIPart;

                                    if (hasPlan) {
                                        // Add to Execution Log
                                        let executionLogIndex = newParts.findIndex(p => p.type === 'execution_log');
                                        if (executionLogIndex === -1) {
                                            newParts.push({ type: 'execution_log', parts: [], id: nanoid() });
                                            executionLogIndex = newParts.length - 1;
                                        }

                                        const logParts = [...(newParts[executionLogIndex] as any).parts];
                                        const existingToolIndex = logParts.findIndex(p => p.type === 'tool' && p.tool.toolCallId === toolPartData.toolCallId);

                                        if (existingToolIndex >= 0) {
                                            logParts[existingToolIndex] = { ...logParts[existingToolIndex], tool: toolPartData } as MessagePart;
                                        } else {
                                            logParts.push({ type: 'tool', tool: toolPartData, id: nanoid() });
                                        }
                                        newParts[executionLogIndex] = { ...newParts[executionLogIndex], parts: logParts } as MessagePart;
                                    } else {
                                        // Should probably not happen without a plan in this specific design, but handle fallback
                                        const existingToolIndex = newParts.findIndex(p => p.type === 'tool' && p.tool.toolCallId === toolPartData.toolCallId);
                                        if (existingToolIndex >= 0) {
                                            newParts[existingToolIndex] = { ...newParts[existingToolIndex], tool: toolPartData } as MessagePart;
                                        } else {
                                            newParts.push({ type: 'tool', tool: toolPartData, id: nanoid() });
                                        }
                                    }
                                } else if (data.type === 'done') {
                                    // Close any open streaming reasoning blocks (both top level and inside execution logs)
                                    return {
                                        ...msg,
                                        parts: newParts.map(p => {
                                            if (p.type === 'reasoning') return { ...p, isStreaming: false };
                                            if (p.type === 'execution_log') {
                                                return {
                                                    ...p,
                                                    parts: (p as any).parts.map((lp: any) => lp.type === 'reasoning' ? { ...lp, isStreaming: false } : lp)
                                                };
                                            }
                                            return p;
                                        })
                                    };
                                }

                                return { ...msg, parts: newParts };
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
                role: 'assistant',
                timestamp: new Date(),
                parts: [
                    { type: 'content', content: "Hello! I'm your AI assistant. I can help you with coding questions, explain concepts, and provide guidance on web development topics. What would you like to know?", id: nanoid() },
                    { type: 'source', sources: [{ title: "Getting Started Guide", url: "#" }, { title: "API Documentation", url: "#" }], id: nanoid() }
                ]
            }
        ]);
        setInputValue('');
        setIsTyping(false);
        setStreamingMessageId(null);
    }, []);
    return (
        <div className="mx-auto flex h-full w-full max-w-3xl flex-col overflow-hidden rounded-xl border bg-background shadow-sm">
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
                                    {message.parts.map((part) => {
                                        if (part.type === 'content') {
                                            return <div key={part.id}>{part.content}</div>;
                                        }
                                        return null;
                                    })}
                                    {message.parts.length === 0 && message.role === 'assistant' && <span className="animate-pulse">Thinking...</span>}
                                </MessageContent>
                                <MessageAvatar
                                    src={message.role === 'user' ? 'https://github.com/dovazencot.png' : 'https://github.com/vercel.png'}
                                    name={message.role === 'user' ? 'User' : 'AI'}
                                />
                            </Message>

                            {/* Interleaved Parts */}
                            <div className="ml-10 space-y-4">
                                {message.parts.map((part, index) => {
                                    if (part.type === 'reasoning') {
                                        return (
                                            <Reasoning key={part.id} isStreaming={part.isStreaming} defaultOpen={false}>
                                                <ReasoningTrigger />
                                                <ReasoningContent>{part.content}</ReasoningContent>
                                            </Reasoning>
                                        );
                                    }
                                    if (part.type === 'tool') {
                                        return (
                                            <Tool key={part.id} defaultOpen={false}>
                                                <ToolHeader
                                                    type="tool-call"
                                                    state={part.tool.state}
                                                    className="bg-muted/40"
                                                />
                                                <ToolContent>
                                                    <ToolInput input={part.tool.input} />
                                                    {'result' in part.tool && !!part.tool.result && (
                                                        <ToolOutput output={JSON.stringify(JSON.parse(part.tool.result as string), null, 2)} errorText={undefined} />
                                                    )}
                                                </ToolContent>
                                            </Tool>
                                        );
                                    }
                                    if (part.type === 'task') {
                                        return (
                                            <div key={part.id} className="space-y-2">
                                                {part.tasks.map((task, tIndex) => (
                                                    <Task key={tIndex} defaultOpen={true}>
                                                        <TaskTrigger title={task.title} />
                                                        <TaskContent>
                                                            {task.items.map((item, iIndex) => (
                                                                <TaskItem key={iIndex}>
                                                                    {item}
                                                                </TaskItem>
                                                            ))}
                                                        </TaskContent>
                                                    </Task>
                                                ))}
                                            </div>
                                        );
                                    }
                                    if (part.type === 'execution_log') {
                                        return (
                                            <Collapsible key={part.id} defaultOpen={false} className="rounded-md border bg-muted/50">
                                                <CollapsibleTrigger className="flex w-full items-center justify-between border-b px-3 py-2 group">
                                                    <div className="flex items-center gap-2">
                                                        <div className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
                                                        <span className="font-medium text-xs text-muted-foreground uppercase">Execution Log</span>
                                                    </div>
                                                    <ChevronDownIcon className="size-4 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
                                                </CollapsibleTrigger>
                                                <CollapsibleContent>
                                                    <div className="max-h-[200px] space-y-4 overflow-y-auto p-3">
                                                        {(part as any).parts.map((innerPart: MessagePart) => {
                                                            if (innerPart.type === 'reasoning') {
                                                                return (
                                                                    <div key={innerPart.id} className="text-muted-foreground text-xs italic">
                                                                        {innerPart.content}
                                                                    </div>
                                                                );
                                                            }
                                                            if (innerPart.type === 'tool') {
                                                                return (
                                                                    <Tool key={innerPart.id} defaultOpen={false} className="mb-0">
                                                                        <ToolHeader
                                                                            type="tool-call"
                                                                            toolName={(innerPart.tool as any).toolName}
                                                                            state={innerPart.tool.state}
                                                                            className="bg-background py-2"
                                                                        />
                                                                        <ToolContent>
                                                                            <ToolInput input={innerPart.tool.input} />
                                                                            {'result' in innerPart.tool && !!innerPart.tool.result && (
                                                                                <ToolOutput output={JSON.stringify(JSON.parse(innerPart.tool.result as string), null, 2)} errorText={undefined} />
                                                                            )}
                                                                        </ToolContent>
                                                                    </Tool>
                                                                );
                                                            }
                                                            return null;
                                                        })}
                                                    </div>
                                                </CollapsibleContent>
                                            </Collapsible>
                                        );
                                    }
                                    if (part.type === 'source') {
                                        return (
                                            <Sources key={part.id}>
                                                <SourcesTrigger count={part.sources.length} />
                                                <SourcesContent>
                                                    {part.sources.map((source, sIndex) => (
                                                        <Source key={sIndex} href={source.url} title={source.title} />
                                                    ))}
                                                </SourcesContent>
                                            </Sources>
                                        );
                                    }
                                    return null; // Content is handled inside Message
                                })}
                            </div>
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