import React from 'react';
import { Wrench, Search, Zap, MessageSquare, Scissors, Video, BarChart2, Film, Sparkles, Eye, ImageIcon, Languages } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import Navigation from '../components/Navigation';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

const TOOLS = [
    {
        id: 1,
        name: 'Transcript Search',
        description: 'Search through video transcripts using natural language. Find specific moments, topics, or speakers in your videos.',
        icon: Search,
        color: 'blue'
    },
    {
        id: 2,
        name: 'Summarizer',
        description: 'Generate concise summaries of video content. Get the key points and main ideas in seconds.',
        icon: MessageSquare,
        color: 'purple'
    },
    {
        id: 3,
        name: 'Highlight Extractor',
        description: 'Automatically extract key moments and create highlight reels. Perfect for social media and compilations.',
        icon: Scissors,
        color: 'pink'
    },
    {
        id: 4,
        name: 'Q&A Engine',
        description: 'Ask questions about video content. Get detailed answers with timestamps and context.',
        icon: Zap,
        color: 'cyan'
    },
    {
        id: 5,
        name: 'Video Trimmer',
        description: 'Precisely trim any video to a specific timeframe. High-quality export with perfect frame accuracy.',
        icon: Video,
        color: 'orange'
    },
    {
        id: 6,
        name: 'Mention Analysis',
        description: 'Deep-scan videos for specific terms or concepts. Get detailed frequency counts and time distribution charts.',
        icon: BarChart2,
        color: 'emerald'
    },
    {
        id: 7,
        name: 'Smart Clip Generator',
        description: 'Batch process and export individual clips for every mention of your chosen topics automatically.',
        icon: Film,
        color: 'indigo'
    },
    {
        id: 8,
        name: 'Viral Shorts Creator',
        description: 'AI Director scans for viral hooks and creates optimized 9:16 vertical shorts for social media.',
        icon: Sparkles,
        color: 'rose'
    },
    {
        id: 9,
        name: 'Visual Scene Search',
        description: 'Search what was SHOWN in the video — charts, graphics, scenes, people, locations. Uses NVIDIA multimodal AI to understand visual content.',
        icon: Eye,
        color: 'violet'
    },
    {
        id: 10,
        name: 'Visual Indexing',
        description: 'Automatically extracts keyframes from videos and generates visual embeddings. Enables image-based search across all your video content.',
        icon: ImageIcon,
        color: 'amber'
    },
    {
        id: 11,
        name: 'Auto Language Detection',
        description: 'Automatically detects video language and translates non-English transcripts to English using Google Gemini. Supports Hindi, Urdu, and 50+ languages.',
        icon: Languages,
        color: 'teal'
    }
];

export default function ToolsPage() {
    const isDark = true;

    const colorClasses = {
        blue: { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/20' },
        purple: { bg: 'bg-purple-500/20', text: 'text-purple-400', border: 'border-purple-500/20' },
        pink: { bg: 'bg-pink-500/20', text: 'text-pink-400', border: 'border-pink-500/20' },
        cyan: { bg: 'bg-cyan-500/20', text: 'text-cyan-400', border: 'border-cyan-500/20' },
        orange: { bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500/20' },
        emerald: { bg: 'bg-emerald-500/20', text: 'text-emerald-400', border: 'border-emerald-500/20' },
        indigo: { bg: 'bg-indigo-500/20', text: 'text-indigo-400', border: 'border-indigo-500/20' },
        rose: { bg: 'bg-rose-500/20', text: 'text-rose-400', border: 'border-rose-500/20' },
        violet: { bg: 'bg-violet-500/20', text: 'text-violet-400', border: 'border-violet-500/20' },
        amber: { bg: 'bg-amber-500/20', text: 'text-amber-400', border: 'border-amber-500/20' },
        teal: { bg: 'bg-teal-500/20', text: 'text-teal-400', border: 'border-teal-500/20' }
    };

    return (
        <div className={cn('flex flex-col h-screen', isDark ? 'bg-slate-950' : 'bg-slate-50', isDark ? 'text-slate-200' : 'text-slate-800')}>
            <Navigation />

            <main className="flex-1 overflow-y-auto p-8">
                <div className="max-w-6xl mx-auto">
                    {/* Header */}
                    <div className="mb-12">
                        <div className="flex items-center gap-4 mb-4">
                            <div className="p-3 rounded-lg bg-cyan-500/20">
                                <Wrench className="w-8 h-8 text-cyan-400" />
                            </div>
                            <div>
                                <h1 className="text-4xl font-bold">Available Tools</h1>
                                <p className="text-sm opacity-60 mt-2">Explore all AI-powered video analysis capabilities</p>
                            </div>
                        </div>
                    </div>

                    {/* Tools Grid */}
                    <div className="grid md:grid-cols-2 gap-8">
                        {TOOLS.map((tool) => {
                            const Icon = tool.icon;
                            const colors = colorClasses[tool.color as keyof typeof colorClasses];

                            return (
                                <div
                                    key={tool.id}
                                    className={cn(
                                        'p-8 rounded-2xl border transition-all',
                                        isDark ? `bg-slate-800/30 ${colors.border}` : `bg-slate-200/30 border-slate-200/30`,
                                        'hover:scale-105 hover:shadow-lg'
                                    )}
                                >
                                    <div className={cn('w-14 h-14 rounded-xl flex items-center justify-center mb-4', colors.bg)}>
                                        <Icon className={cn('w-7 h-7', colors.text)} />
                                    </div>

                                    <h3 className="text-xl font-bold mb-3">{tool.name}</h3>
                                    <p className="text-sm opacity-75 leading-relaxed mb-6">{tool.description}</p>

                                    <div className="flex flex-wrap gap-2">
                                        <span className={cn('px-3 py-1 rounded-full text-xs font-semibold', colors.bg, colors.text)}>
                                            {tool.color.charAt(0).toUpperCase() + tool.color.slice(1)}
                                        </span>
                                        <span className={cn('px-3 py-1 rounded-full text-xs font-semibold', isDark ? 'bg-slate-700/30' : 'bg-slate-300/30', 'text-slate-400')}>
                                            AI Powered
                                        </span>
                                    </div>

                                    <a
                                        href="/chatbot"
                                        className={cn('block mt-6 w-full py-2 rounded-lg text-center font-semibold transition-all', colors.bg, colors.text, 'hover:opacity-80')}
                                    >
                                        Use in Chat →
                                    </a>
                                </div>
                            );
                        })}
                    </div>

                    {/* How to Use Section */}
                    <div className={cn('mt-16 p-8 rounded-2xl', isDark ? 'bg-slate-800/20 border border-slate-700/30' : 'bg-slate-200/20 border border-slate-200/30')}>
                        <h2 className="text-2xl font-bold mb-6">How to Use These Tools</h2>

                        <div className="grid md:grid-cols-2 gap-8">
                            <div>
                                <h3 className="font-semibold text-lg mb-3 flex items-center gap-2">
                                    <span className="w-6 h-6 rounded-full bg-blue-500/30 flex items-center justify-center text-sm">1</span>
                                    Select a Video
                                </h3>
                                <p className="opacity-75 text-sm leading-relaxed">
                                    Go to the chatbot and select one of your processed videos from the left sidebar, or paste a new YouTube URL to process.
                                </p>
                            </div>

                            <div>
                                <h3 className="font-semibold text-lg mb-3 flex items-center gap-2">
                                    <span className="w-6 h-6 rounded-full bg-purple-500/30 flex items-center justify-center text-sm">2</span>
                                    Ask a Question
                                </h3>
                                <p className="opacity-75 text-sm leading-relaxed">
                                    Type your question or request in the chat. Be specific about what you want to find or create.
                                </p>
                            </div>

                            <div>
                                <h3 className="font-semibold text-lg mb-3 flex items-center gap-2">
                                    <span className="w-6 h-6 rounded-full bg-pink-500/30 flex items-center justify-center text-sm">3</span>
                                    Watch the Magic
                                </h3>
                                <p className="opacity-75 text-sm leading-relaxed">
                                    The AI will process your request and show you the results. Watch the process overview on the right to see what's happening.
                                </p>
                            </div>

                            <div>
                                <h3 className="font-semibold text-lg mb-3 flex items-center gap-2">
                                    <span className="w-6 h-6 rounded-full bg-cyan-500/30 flex items-center justify-center text-sm">4</span>
                                    Explore Results
                                </h3>
                                <p className="opacity-75 text-sm leading-relaxed">
                                    View clips in the clips store, browse videos, or ask follow-up questions. Everything is connected!
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Examples Section */}
                    <div className={cn('mt-8 p-8 rounded-2xl', isDark ? 'bg-slate-800/20 border border-slate-700/30' : 'bg-slate-200/20 border border-slate-200/30')}>
                        <h2 className="text-2xl font-bold mb-6">Example Queries</h2>

                        <div className="grid md:grid-cols-2 gap-6">
                            <div className={cn('p-4 rounded-lg', isDark ? 'bg-slate-700/20' : 'bg-slate-300/20')}>
                                <p className="font-semibold text-sm mb-2">Search</p>
                                <p className="text-sm opacity-75">
                                    "Find all mentions of AI in this video and show me the timestamps"
                                </p>
                            </div>

                            <div className={cn('p-4 rounded-lg', isDark ? 'bg-slate-700/20' : 'bg-slate-300/20')}>
                                <p className="font-semibold text-sm mb-2">Summarize</p>
                                <p className="text-sm opacity-75">
                                    "Give me a 3-point summary of the main topics covered"
                                </p>
                            </div>

                            <div className={cn('p-4 rounded-lg', isDark ? 'bg-slate-700/20' : 'bg-slate-300/20')}>
                                <p className="font-semibold text-sm mb-2">Highlights</p>
                                <p className="text-sm opacity-75">
                                    "Create 3 different highlight clips focusing on key moments"
                                </p>
                            </div>

                            <div className={cn('p-4 rounded-lg', isDark ? 'bg-slate-700/20' : 'bg-slate-300/20')}>
                                <p className="font-semibold text-sm mb-2">Q&A</p>
                                <p className="text-sm opacity-75">
                                    "What are the main conclusions from this discussion?"
                                </p>
                            </div>

                            <div className={cn('p-4 rounded-lg', isDark ? 'bg-slate-700/20' : 'bg-slate-300/20')}>
                                <p className="font-semibold text-sm mb-2">Visual Search</p>
                                <p className="text-sm opacity-75">
                                    "Was there a map or chart shown in the video?"
                                </p>
                            </div>

                            <div className={cn('p-4 rounded-lg', isDark ? 'bg-slate-700/20' : 'bg-slate-300/20')}>
                                <p className="font-semibold text-sm mb-2">Semantic Mentions</p>
                                <p className="text-sm opacity-75">
                                    "How many times does the speaker discuss economic policy?"
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* CTA */}
                    <div className="mt-12 text-center">
                        <a
                            href="/chatbot"
                            className="inline-block px-8 py-4 rounded-lg bg-gradient-to-r from-blue-500 to-purple-500 text-white font-semibold hover:shadow-lg transition-all hover:scale-105"
                        >
                            Start Using Tools →
                        </a>
                    </div>
                </div>
            </main>
        </div>
    );
}
