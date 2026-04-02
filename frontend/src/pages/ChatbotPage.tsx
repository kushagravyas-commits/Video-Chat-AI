import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
    Brain,
    Send,
    CheckCircle2,
    Loader2,
    Clock,
    Zap,
    Sparkles,
    Moon,
    Sun,
    Palette,
    Film,
    X,
    Plus,
    ChevronDown,
    Trash2,
    Check,
    Bot
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import Navigation from '../components/Navigation';
import VideoSelectModal from '../components/VideoSelectModal';
import MentionResultsCard, { type MentionResult } from '../components/MentionResultsCard';
import { ClipOptionsCard } from '../components/ClipOptionsCard';
import ReactMarkdown from 'react-markdown';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

type Theme = 'dark' | 'light';
type ColorTheme = 'blue' | 'purple' | 'cyan' | 'emerald' | 'rose';

const THEME_COLORS = {
    blue: { primary: '#3b82f6', secondary: '#60a5fa', accent: '#0ea5e9' },
    purple: { primary: '#a855f7', secondary: '#d946ef', accent: '#ec4899' },
    cyan: { primary: '#0891b2', secondary: '#06b6d4', accent: '#14b8a6' },
    emerald: { primary: '#10b981', secondary: '#34d399', accent: '#059669' },
    rose: { primary: '#f43f5e', secondary: '#fb7185', accent: '#e11d48' },
};

interface Message {
    role: 'user' | 'assistant';
    content: string;
    isHiddenCommand?: boolean;
}

interface ToolEvent {
    type: 'status' | 'tool_start' | 'tool_result' | 'answer' | 'error';
    content?: string;
    tool?: string;
    args?: any;
    result?: any;
}

interface VideoEntry {
    id: string;
    title: string;
    channel?: string;
    youtube_url?: string;
}

interface ClipOptions {
    total_mentions: number;
}

export default function ChatbotPage() {
    const [searchParams] = useSearchParams();
    const [theme, setTheme] = useState<Theme>('dark');
    const [colorTheme, setColorTheme] = useState<ColorTheme>('blue');
    const [showThemeMenu, setShowThemeMenu] = useState(false);

    const [allVideos, setAllVideos] = useState<VideoEntry[]>([]);
    const [referenceVideoIds, setReferenceVideoIds] = useState<string[]>(() => {
        const saved = sessionStorage.getItem('chat_referenceVideoIds');
        return saved ? JSON.parse(saved) : [];
    });
    const [activeVideoId, setActiveVideoId] = useState<string | null>(() => {
        return sessionStorage.getItem('chat_activeVideoId') || null;
    });
    const [messages, setMessages] = useState<Message[]>(() => {
        const saved = sessionStorage.getItem('chat_messages');
        return saved ? JSON.parse(saved) : [];
    });
    const [input, setInput] = useState('');
    const [isThinking, setIsThinking] = useState(false);
    const [toolLogs, setToolLogs] = useState<ToolEvent[]>([]);
    const [showAddVideoDropdown, setShowAddVideoDropdown] = useState(false);

    const chatEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, isThinking]);

    // Fetch all videos
    useEffect(() => {
        fetch('/api/videos')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    setAllVideos(data.videos);
                }
            });
    }, []);

    // Auto-select video from URL parameter
    useEffect(() => {
        const videoParam = searchParams.get('video');
        if (videoParam) {
            setActiveVideoId(videoParam);
            // Also add it to reference videos if not already there
            if (!referenceVideoIds.includes(videoParam)) {
                setReferenceVideoIds([videoParam]);
            }
        }
    }, [searchParams]);

    // Sync state to sessionStorage
    useEffect(() => {
        sessionStorage.setItem('chat_referenceVideoIds', JSON.stringify(referenceVideoIds));
    }, [referenceVideoIds]);

    useEffect(() => {
        if (activeVideoId) {
            sessionStorage.setItem('chat_activeVideoId', activeVideoId);
        } else {
            sessionStorage.removeItem('chat_activeVideoId');
        }
    }, [activeVideoId]);

    useEffect(() => {
        sessionStorage.setItem('chat_messages', JSON.stringify(messages));
    }, [messages]);

    const handleAddReferenceVideo = (videoId: string) => {
        if (!referenceVideoIds.includes(videoId) && referenceVideoIds.length < 5) {
            const newReferenceIds = [...referenceVideoIds, videoId];
            setReferenceVideoIds(newReferenceIds);
            setActiveVideoId(videoId);
            setShowAddVideoDropdown(false);
        }
    };

    const handleRemoveReferenceVideo = (videoId: string) => {
        const newReferenceIds = (referenceVideoIds || []).filter(id => id !== videoId);
        setReferenceVideoIds(newReferenceIds);

        // If removed video was active, switch to another
        if (activeVideoId === videoId && newReferenceIds.length > 0) {
            setActiveVideoId(newReferenceIds[0]);
        } else if (newReferenceIds.length === 0) {
            setActiveVideoId(null);
        }
    };

    const handleSendMessage = async (e?: React.FormEvent, hiddenCommand?: string) => {
        e?.preventDefault();
        
        const userMsg = hiddenCommand || input.trim();
        if (!userMsg || isThinking) return;

        if (!hiddenCommand) {
            setInput('');
        }
        
        setMessages(prev => [...prev, { 
            role: 'user', 
            content: hiddenCommand ? "Generating clips with your selected settings..." : userMsg,
            isHiddenCommand: !!hiddenCommand
        }]);
        
        setIsThinking(true);
        setToolLogs([]);

        try {
            const response = await fetch('/api/agent-chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: userMsg,
                    video_id: activeVideoId,
                    video_ids: (referenceVideoIds || []).filter(id => id && allVideos.some(v => v.id === id))
                })
            });

            const reader = response.body?.getReader();
            if (!reader) throw new Error('No stream');

            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data: ToolEvent = JSON.parse(line.slice(6));
                        handleAgentEvent(data);
                    }
                }
            }
        } catch (err) {
            console.error('Chat error:', err);
            setMessages(prev => [...prev, { role: 'assistant', content: "Sorry, I lost connection to the brain." }]);
        } finally {
            setIsThinking(false);
        }
    };

    const handleAgentEvent = (event: ToolEvent) => {
        if (event.type === 'answer') {
            setMessages(prev => [...prev, { role: 'assistant', content: event.content || '' }]);
        } else if (event.type === 'error') {
            setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${event.content}` }]);
        } else {
            setToolLogs(prev => [...prev, event]);
        }
    };

    const getVideoTitle = (videoId: string) => {
        return allVideos.find(v => v.id === videoId)?.title || videoId;
    };

    const getVideoChannel = (videoId: string) => {
        return allVideos.find(v => v.id === videoId)?.channel;
    };

    // Helper function to parse mention results from message content
    const parseMentionResults = (content: string): MentionResult | null => {
        try {
            const jsonMatch = content.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
            if (jsonMatch) {
                const jsonStr = jsonMatch[1];
                const parsed = JSON.parse(jsonStr);
                if (parsed.type === 'mention_results') {
                    return parsed.data as MentionResult;
                }
            }
        } catch (e) {
            console.error('Failed to parse mention results:', e);
        }
        return null;
    };

    const parseClipOptions = (content: string): ClipOptions | null => {
        try {
            const jsonMatch = content.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
            if (jsonMatch) {
                let jsonStr = jsonMatch[1];
                const parsed = JSON.parse(jsonStr);
                if (parsed.type === 'clip_options') {
                    return parsed.data as ClipOptions;
                }
            }
        } catch (e) {
            // fail silently
        }
        return null;
    };

    const handleGenerateClips = (options: { quantity: number; grouping: boolean; style: string }) => {
        const cmd = `[SYSTEM COMMAND EXECUTED BY USER UI]\nAction: Extract top ${options.quantity} mentions into clips.\nGrouping: ${options.grouping}\nStyle: ${options.style}\nProceed immediately with "create_clips_from_mentions" without asking any questions.`;
        handleSendMessage(undefined, cmd);
    };

    // Helper function to remove JSON block from content for display
    const removeJsonBlock = (content: string) => {
        return content.replace(/```(?:json)?\s*[\s\S]*?\s*```/ig, '').trim();
    };

    const availableVideos = allVideos.filter(v => !(referenceVideoIds || []).includes(v.id));

    const isDark = theme === 'dark';
    const colors = THEME_COLORS[colorTheme];
    const bgColor = isDark ? 'bg-slate-950' : 'bg-slate-50';
    const textColor = isDark ? 'text-slate-200' : 'text-slate-800';
    const sidebarBg = isDark ? 'bg-slate-900/40' : 'bg-white/40';
    const borderColor = isDark ? 'border-slate-700/30' : 'border-slate-200/30';
    const glassClass = isDark ? 'glass-dark' : 'glass-light';

    return (
        <div className={cn('flex flex-col h-screen', bgColor, textColor)}>
            <Navigation />

            <div className="flex flex-1 overflow-hidden">
                {/* LEFT SIDEBAR: Reference Videos */}
                <aside className={cn('w-64', glassClass, 'border-r', borderColor, 'flex flex-col overflow-hidden')}>
                    {/* Header */}
                    <div className={cn('p-5 border-b', borderColor, 'shrink-0')}>
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-bold flex items-center gap-2">
                                <Film className="w-5 h-5" style={{ color: colors.primary }} />
                                References
                            </h2>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => {
                                        if (referenceVideoIds.length > 0 && window.confirm('Remove all reference videos?')) {
                                            setReferenceVideoIds([]);
                                            setActiveVideoId(null);
                                        }
                                    }}
                                    className={cn(
                                        'p-2 rounded-lg transition-colors cursor-pointer',
                                        isDark ? 'hover:bg-slate-800' : 'hover:bg-slate-200'
                                    )}
                                    title="Remove all references"
                                >
                                    <Trash2 className="w-4 h-4 text-red-400" />
                                </button>
                                <div
                                    onClick={() => setShowThemeMenu(!showThemeMenu)}
                                    className={cn(
                                        'p-2 rounded-lg transition-colors relative cursor-pointer',
                                        isDark ? 'hover:bg-slate-800' : 'hover:bg-slate-200'
                                    )}
                                >
                                    <Palette className="w-4 h-4" />

                                {showThemeMenu && (
                                    <div
                                        className={cn(
                                            'absolute right-0 top-full mt-2 p-3 rounded-xl shadow-2xl z-50',
                                            isDark ? 'bg-slate-900' : 'bg-white',
                                            borderColor, 'border'
                                        )}
                                        onClick={e => e.stopPropagation()}
                                    >
                                        <div className="text-xs font-semibold mb-2 opacity-50">Theme</div>
                                        <div className="flex gap-2 mb-3">
                                            <button onClick={() => setTheme('dark')} className={cn('p-1.5 rounded', theme === 'dark' ? 'bg-slate-700' : 'opacity-50')}>
                                                <Moon className="w-4 h-4" />
                                            </button>
                                            <button onClick={() => setTheme('light')} className={cn('p-1.5 rounded', theme === 'light' ? 'bg-slate-300' : 'opacity-50')}>
                                                <Sun className="w-4 h-4" />
                                            </button>
                                        </div>
                                        <div className="text-xs font-semibold mb-2 opacity-50">Color</div>
                                        <div className="grid grid-cols-3 gap-2">
                                            {(Object.keys(THEME_COLORS) as ColorTheme[]).map(ct => (
                                                <button
                                                    key={ct}
                                                    onClick={() => { setColorTheme(ct); setShowThemeMenu(false); }}
                                                    className={cn(
                                                        'w-full h-6 rounded-lg transition-all',
                                                        colorTheme === ct ? 'ring-2 ring-offset-2 ring-offset-slate-900 scale-110' : 'opacity-60'
                                                    )}
                                                    style={{ backgroundColor: THEME_COLORS[ct].primary }}
                                                />
                                            ))}
                                        </div>
                                    </div>
                                )}
                                </div>
                            </div>
                        </div>

                        {/* Add Video Dropdown */}
                        <div className="relative">
                            <button
                                onClick={() => setShowAddVideoDropdown(!showAddVideoDropdown)}
                                disabled={referenceVideoIds.length >= 5}
                                className={cn(
                                    'w-full px-3 py-2 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition-all',
                                    referenceVideoIds.length >= 5
                                        ? 'opacity-50 cursor-not-allowed'
                                        : 'hover:opacity-80'
                                )}
                                style={{
                                    backgroundColor: `${colors.primary}40`,
                                    color: colors.primary
                                }}
                            >
                                <Plus className="w-4 h-4" />
                                Add Video
                            </button>

                            {showAddVideoDropdown && (
                                <div className={cn(
                                    'absolute top-full left-0 right-0 mt-2 rounded-lg shadow-2xl z-50 max-h-64 overflow-y-auto',
                                    isDark ? 'bg-slate-900' : 'bg-white',
                                    'border', borderColor
                                )}>
                                    {availableVideos.length === 0 ? (
                                        <div className="p-3 text-xs text-center opacity-50">
                                            All videos added or no videos available
                                        </div>
                                    ) : (
                                        availableVideos.map(video => (
                                            <button
                                                key={video.id}
                                                onClick={() => handleAddReferenceVideo(video.id)}
                                                className={cn(
                                                    'w-full text-left px-3 py-2 text-xs border-b',
                                                    borderColor,
                                                    'hover:opacity-80 transition-opacity'
                                                )}
                                            >
                                                <p className="font-semibold truncate">{video.title}</p>
                                                {video.channel && <p className="opacity-60 truncate">{video.channel}</p>}
                                            </button>
                                        ))
                                    )}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Reference Videos List */}
                    <div className="flex-1 overflow-y-auto scrollbar-thin p-3 space-y-2">
                        {referenceVideoIds.filter(id => allVideos.some(v => v.id === id)).length === 0 ? (
                            <div className="h-40 flex flex-col items-center justify-center text-center opacity-50">
                                <Film className="w-8 h-8 mb-2" />
                                <p className="text-xs font-semibold">No reference videos</p>
                                <p className="text-[10px] mt-2">Add videos to get started</p>
                            </div>
                        ) : (
                            referenceVideoIds
                                .filter(id => allVideos.some(v => v.id === id))
                                .map((videoId) => (
                                <div
                                    key={videoId}
                                    onClick={() => setActiveVideoId(videoId)}
                                    className={cn(
                                        'w-full text-left p-3 rounded-lg transition-all relative group cursor-pointer',
                                        activeVideoId === videoId ? 'ring-2' : 'hover:opacity-80'
                                    )}
                                    style={{
                                        backgroundColor: activeVideoId === videoId ? `${colors.primary}20` : 'transparent',
                                        ringColor: activeVideoId === videoId ? colors.primary : 'transparent'
                                    }}
                                >
                                    <div className="flex items-start gap-2">
                                        {activeVideoId === videoId && (
                                            <div className="p-2 rounded-lg shrink-0" style={{ backgroundColor: `${colors.primary}40` }}>
                                                <Film className="w-3.5 h-3.5 fill-current" style={{ color: colors.primary }} />
                                            </div>
                                        )}
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-semibold truncate">{getVideoTitle(videoId)}</p>
                                            {getVideoChannel(videoId) && (
                                                <p className="text-[10px] opacity-60 truncate mt-0.5">{getVideoChannel(videoId)}</p>
                                            )}
                                        </div>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                handleRemoveReferenceVideo(videoId);
                                            }}
                                            className={cn(
                                                'p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity',
                                                isDark ? 'hover:bg-slate-700' : 'hover:bg-slate-200'
                                            )}
                                        >
                                            <X className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>

                    {/* Footer */}
                    <div className={cn('p-3 border-t', borderColor, isDark ? 'bg-slate-900/20' : 'bg-slate-200/20')}>
                        <div className="flex items-center gap-2 text-xs opacity-50">
                            <span className="w-2 h-2 rounded-full bg-green-500 animate-glow"></span>
                            <span>System Ready</span>
                        </div>
                    </div>
                </aside>

                {/* CENTER: Chat Interface */}
                <main className="flex-1 flex flex-col relative">
                    {/* Chat Area */}
                    <div className="flex-1 overflow-y-auto scrollbar-thin p-8 space-y-6">
                        {messages.length === 0 && (
                            <div className="h-full flex flex-col items-center justify-center">
                                <div className="relative mb-4">
                                    <div
                                        className="absolute inset-0 rounded-full blur-3xl opacity-20 animate-pulse"
                                        style={{ backgroundColor: colors.primary }}
                                    />
                                    <Brain className="w-16 h-16 relative z-10 opacity-40" />
                                </div>
                                <div className="text-center max-w-md">
                                    <p className="text-xl font-semibold mb-2">Chat with Your Videos</p>
                                    <p className="text-sm opacity-60">
                                        {referenceVideoIds.length === 0
                                            ? 'Add reference videos from the left sidebar to get started.'
                                            : 'Ask questions about the reference videos. I can search across multiple videos at once!'}
                                    </p>
                                </div>
                            </div>
                        )}

                        {messages.map((msg, i) => {
                            const mentionData = msg.role === 'assistant' ? parseMentionResults(msg.content) : null;
                            const clipOptionsData = msg.role === 'assistant' ? parseClipOptions(msg.content) : null;
                            
                            // If it's a hidden system command, style it like a system notification
                            if (msg.isHiddenCommand) {
                                return (
                                    <div key={i} className="flex justify-center my-4 animate-fade-in opacity-70">
                                        <div className="bg-slate-800 text-slate-400 text-xs px-3 py-1.5 rounded-full flex items-center gap-2 border border-slate-700">
                                            <Check className="w-3 h-3" />
                                            {msg.content}
                                        </div>
                                    </div>
                                );
                            }

                            return (
                                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-fade-in`}>
                                    {msg.role === 'assistant' && (
                                        <div className={cn(`w-8 h-8 rounded-full flex items-center justify-center mr-3 mt-1 flex-shrink-0 shadow-lg`)} style={{ backgroundColor: colors.secondary }}>
                                            <Bot className="w-5 h-5 text-white" />
                                        </div>
                                    )}
                                    <div className={cn(`max-w-[85%] rounded-2xl px-5 py-3.5 shadow-sm`,
                                        msg.role === 'user'
                                            ? `text-white selection:bg-white/30 rounded-br-sm`
                                            : `${isDark ? 'bg-slate-800 text-slate-200' : 'bg-white text-slate-800'} border ${isDark ? 'border-slate-700' : 'border-slate-200'} rounded-bl-sm`
                                    )} style={{ backgroundColor: msg.role === 'user' ? colors.primary : undefined }}>
                                        {msg.role === 'assistant' ? (
                                            <div className="space-y-4">
                                                {/* Only show text if there isn't a strict UI replacement OR if they still want to type something before it */}
                                                {(!mentionData && !clipOptionsData && removeJsonBlock(msg.content)) && (
                                                    <div className="whitespace-pre-wrap leading-relaxed text-[15px] prose prose-invert max-w-none">
                                                        <ReactMarkdown
                                                            components={{
                                                                a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" download className="text-blue-400 hover:text-blue-300 underline underline-offset-2" />
                                                            }}
                                                        >
                                                            {removeJsonBlock(msg.content)}
                                                        </ReactMarkdown>
                                                    </div>
                                                )}

                                                {/* Render Rich UI Components if JSON was found */}
                                                {mentionData && <MentionResultsCard data={mentionData} />}
                                                {clipOptionsData && (
                                                    <ClipOptionsCard 
                                                        totalMentions={clipOptionsData.total_mentions} 
                                                        onGenerate={handleGenerateClips}
                                                        isGenerating={isThinking}
                                                    />
                                                )}
                                            </div>
                                        ) : (
                                            <div className="whitespace-pre-wrap text-[15px] leading-relaxed relative z-10">{msg.content}</div>
                                        )}
                                    </div>
                                </div>
                            );
                        })}

                        {isThinking && (
                            <div className="flex gap-4 animate-in-up">
                                <div
                                    className="w-10 h-10 rounded-full flex items-center justify-center animate-pulse shadow-lg text-white font-semibold shrink-0"
                                    style={{ backgroundColor: colors.secondary }}
                                >
                                    A
                                </div>
                                <div className={cn('rounded-2xl px-5 py-4', isDark ? 'bg-slate-800/40' : 'bg-slate-200/40', 'flex items-center gap-3')}>
                                    <div className="flex gap-1.5">
                                        <span className="w-2 h-2 bg-current rounded-full animate-bounce [animation-delay:-0.3s]" style={{ color: colors.primary }} />
                                        <span className="w-2 h-2 bg-current rounded-full animate-bounce [animation-delay:-0.15s]" style={{ color: colors.secondary }} />
                                        <span className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ color: colors.accent }} />
                                    </div>
                                    <span className="text-sm font-medium">Thinking...</span>
                                </div>
                            </div>
                        )}
                        <div ref={chatEndRef} />
                    </div>

                    {/* Input Area */}
                    <div className={cn('p-8 border-t flex flex-col gap-2', borderColor, isDark ? 'bg-slate-900/20' : 'bg-slate-200/20')}>
                        {messages.length > 0 && (
                            <div className="flex justify-end w-full">
                                <button
                                    type="button"
                                    onClick={() => {
                                        if (window.confirm('Clear all messages and history?')) {
                                            setMessages([]);
                                            setToolLogs([]);
                                            sessionStorage.removeItem('chat_messages');
                                        }
                                    }}
                                    className="text-xs opacity-50 hover:opacity-100 transition-opacity uppercase tracking-wider font-semibold"
                                >
                                    Clear Chat History
                                </button>
                            </div>
                        )}
                        <form onSubmit={handleSendMessage} className="relative flex items-end gap-3">
                            <textarea
                                rows={1}
                                value={input}
                                onChange={e => setInput(e.target.value)}
                                onKeyDown={e => {
                                    if (e.key === 'Enter' && !e.shiftKey) {
                                        e.preventDefault();
                                        handleSendMessage();
                                    }
                                }}
                                placeholder="Ask me anything or paste a YouTube URL..."
                                className={cn(
                                    'w-full py-3 px-4 rounded-xl text-sm outline-none resize-none',
                                    isDark
                                        ? 'bg-slate-800 border border-slate-700/50 focus:border-blue-500/50'
                                        : 'bg-white border border-slate-300/50 focus:border-blue-500/50'
                                )}
                            />
                            <button
                                type="submit"
                                disabled={isThinking || !input.trim()}
                                className="p-3 rounded-xl text-white transition-all shadow-lg disabled:opacity-50"
                                style={{ backgroundColor: colors.primary }}
                            >
                                <Send className="w-5 h-5" />
                            </button>
                        </form>
                    </div>
                </main>

                {/* RIGHT SIDEBAR: Process Overview */}
                <aside className={cn('w-80', glassClass, 'border-l', borderColor, 'flex flex-col overflow-hidden')}>
                    {/* Header */}
                    <div className={cn('p-5 border-b', borderColor, 'shrink-0')}>
                        <div className="flex items-center gap-3">
                            <div className="p-2.5 rounded-lg" style={{ backgroundColor: `${colors.primary}30` }}>
                                <Zap className="w-5 h-5" style={{ color: colors.primary }} />
                            </div>
                            <div>
                                <h2 className="text-lg font-bold">Process Overview</h2>
                                <p className={cn('text-xs opacity-50 mt-0.5')}>Real-time updates</p>
                            </div>
                        </div>
                    </div>

                    {/* Process List */}
                    <div className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-3">
                        {toolLogs.length === 0 && !isThinking && (
                            <div className="h-full flex flex-col items-center justify-center text-center opacity-50">
                                <Sparkles className="w-8 h-8 mb-2" />
                                <p className="text-xs">No processes running</p>
                            </div>
                        )}

                        {/* Show "Thinking..." when agent is thinking */}
                        {isThinking && toolLogs.length === 0 && (
                            <div className={cn('flex items-center gap-2 p-3 rounded-lg animate-pulse', isDark ? 'bg-slate-800/30' : 'bg-slate-200/30')}>
                                <Brain className="w-3.5 h-3.5 shrink-0" style={{ color: colors.primary }} />
                                <span className="font-medium text-sm">Thinking...</span>
                            </div>
                        )}

                        {/* Show all process events */}
                        {toolLogs.map((log, i) => (
                            <div key={i} className="animate-in-right text-xs">
                                {log.type === 'status' && (
                                    <div className={cn('flex items-start gap-2 p-3 rounded-lg', isDark ? 'bg-slate-800/30' : 'bg-slate-200/30')}>
                                        <Clock className="w-3.5 h-3.5 mt-0.5 shrink-0 opacity-50" />
                                        <span className="opacity-75">{log.content}</span>
                                    </div>
                                )}
                                {log.type === 'tool_start' && (
                                    <div className={cn('space-y-2 p-3 rounded-lg', isDark ? 'bg-blue-950/30' : 'bg-blue-100/30', 'border', 'border-blue-500/20')}>
                                        <div className="flex items-center gap-2" style={{ color: colors.primary }}>
                                            <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                                            <span className="font-bold uppercase tracking-wide">{log.tool}</span>
                                        </div>
                                    </div>
                                )}
                                {log.type === 'tool_result' && (
                                    <div className={cn('flex items-center gap-2 p-3 rounded-lg', isDark ? 'bg-green-950/30' : 'bg-green-100/30', 'border border-green-500/20')}>
                                        <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-green-500" />
                                        <span className="font-bold uppercase tracking-wide">{log.tool}</span>
                                    </div>
                                )}
                                {log.type === 'error' && (
                                    <div className={cn('flex items-center gap-2 p-3 rounded-lg', isDark ? 'bg-red-950/30' : 'bg-red-100/30', 'border border-red-500/20')}>
                                        <span className="w-3.5 h-3.5 shrink-0 text-red-500">⚠</span>
                                        <span className="font-semibold text-red-400">{log.content}</span>
                                    </div>
                                )}
                            </div>
                        ))}

                        {isThinking && toolLogs.length > 0 && (
                            <div className={cn('flex items-center gap-2 p-3 rounded-lg animate-pulse', isDark ? 'bg-slate-800/30' : 'bg-slate-200/30')}>
                                <Loader2 className="w-3 h-3 animate-spin shrink-0" style={{ color: colors.primary }} />
                                <span className="font-medium text-sm">Processing...</span>
                            </div>
                        )}
                    </div>

                    {/* Footer */}
                    <div className={cn('p-4 border-t', borderColor, isDark ? 'bg-slate-900/20' : 'bg-slate-200/20')}>
                        <div className="flex items-center justify-between text-[10px] opacity-50">
                            <span className="flex items-center gap-1.5">
                                <span className="w-2 h-2 rounded-full bg-green-500 animate-glow"></span>
                                Connected
                            </span>
                            <span className="font-mono">v1.0</span>
                        </div>
                    </div>
                </aside>
            </div>
        </div>
    );
}
