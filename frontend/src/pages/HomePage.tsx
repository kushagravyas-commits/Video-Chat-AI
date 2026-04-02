import React from 'react';
import { Link } from 'react-router-dom';
import { MessageSquare, Video, Scissors, Wrench, ArrowRight } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

export default function HomePage() {
    const isDark = true;

    return (
        <div className={cn('min-h-screen', isDark ? 'bg-slate-950' : 'bg-slate-50', isDark ? 'text-slate-200' : 'text-slate-800')}>
            {/* Header */}
            <div className={cn('border-b', isDark ? 'border-slate-700/30 bg-slate-900/40' : 'border-slate-200/30 bg-white/40', 'backdrop-blur-md')}>
                <div className="max-w-7xl mx-auto px-8 py-6">
                    <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-lg bg-blue-500/20">
                            <Video className="w-6 h-6 text-blue-400" />
                        </div>
                        <h1 className="text-3xl font-bold">Video Vault</h1>
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-8 py-16">
                <div className="text-center mb-16">
                    <h2 className="text-5xl font-bold mb-4">Welcome to Video Vault</h2>
                    <p className="text-xl opacity-75 max-w-2xl mx-auto">
                        Manage your videos, explore highlights, and chat with AI about your content in one powerful platform.
                    </p>
                </div>

                {/* Cards Grid */}
                <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
                    {/* Chatbot Card */}
                    <Link
                        to="/chatbot"
                        className={cn(
                            'p-8 rounded-2xl transition-all group cursor-pointer',
                            'hover:scale-105 hover:shadow-2xl',
                            isDark ? 'bg-blue-950/30 border border-blue-500/20 hover:border-blue-500/40' : 'bg-blue-100/20 border border-blue-200/30'
                        )}
                    >
                        <div className="flex items-start gap-4">
                            <div className="p-4 rounded-xl bg-blue-500/20 group-hover:bg-blue-500/30 transition-colors">
                                <MessageSquare className="w-8 h-8 text-blue-400" />
                            </div>
                            <div className="flex-1">
                                <h3 className="text-2xl font-bold mb-2 flex items-center gap-2">
                                    Chat with Videos
                                    <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                                </h3>
                                <p className="opacity-75">Ask questions about your videos, get summaries, and generate highlights using AI.</p>
                                <div className="mt-4 text-sm font-semibold text-blue-400">Go to Chatbot →</div>
                            </div>
                        </div>
                    </Link>

                    {/* Videos Store Card */}
                    <Link
                        to="/videos"
                        className={cn(
                            'p-8 rounded-2xl transition-all group cursor-pointer',
                            'hover:scale-105 hover:shadow-2xl',
                            isDark ? 'bg-purple-950/30 border border-purple-500/20 hover:border-purple-500/40' : 'bg-purple-100/20 border border-purple-200/30'
                        )}
                    >
                        <div className="flex items-start gap-4">
                            <div className="p-4 rounded-xl bg-purple-500/20 group-hover:bg-purple-500/30 transition-colors">
                                <Video className="w-8 h-8 text-purple-400" />
                            </div>
                            <div className="flex-1">
                                <h3 className="text-2xl font-bold mb-2 flex items-center gap-2">
                                    Videos Store
                                    <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                                </h3>
                                <p className="opacity-75">Browse and manage all your processed videos with titles, channels, and metadata.</p>
                                <div className="mt-4 text-sm font-semibold text-purple-400">View Videos →</div>
                            </div>
                        </div>
                    </Link>

                    {/* Clips Store Card */}
                    <Link
                        to="/clips"
                        className={cn(
                            'p-8 rounded-2xl transition-all group cursor-pointer',
                            'hover:scale-105 hover:shadow-2xl',
                            isDark ? 'bg-pink-950/30 border border-pink-500/20 hover:border-pink-500/40' : 'bg-pink-100/20 border border-pink-200/30'
                        )}
                    >
                        <div className="flex items-start gap-4">
                            <div className="p-4 rounded-xl bg-pink-500/20 group-hover:bg-pink-500/30 transition-colors">
                                <Scissors className="w-8 h-8 text-pink-400" />
                            </div>
                            <div className="flex-1">
                                <h3 className="text-2xl font-bold mb-2 flex items-center gap-2">
                                    Clips Store
                                    <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                                </h3>
                                <p className="opacity-75">Explore all generated highlights and clips from your video library.</p>
                                <div className="mt-4 text-sm font-semibold text-pink-400">View Clips →</div>
                            </div>
                        </div>
                    </Link>

                    {/* Tools Card */}
                    <Link
                        to="/tools"
                        className={cn(
                            'p-8 rounded-2xl transition-all group cursor-pointer',
                            'hover:scale-105 hover:shadow-2xl',
                            isDark ? 'bg-cyan-950/30 border border-cyan-500/20 hover:border-cyan-500/40' : 'bg-cyan-100/20 border border-cyan-200/30'
                        )}
                    >
                        <div className="flex items-start gap-4">
                            <div className="p-4 rounded-xl bg-cyan-500/20 group-hover:bg-cyan-500/30 transition-colors">
                                <Wrench className="w-8 h-8 text-cyan-400" />
                            </div>
                            <div className="flex-1">
                                <h3 className="text-2xl font-bold mb-2 flex items-center gap-2">
                                    Tools
                                    <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                                </h3>
                                <p className="opacity-75">Discover all available AI tools and capabilities for video analysis.</p>
                                <div className="mt-4 text-sm font-semibold text-cyan-400">Explore Tools →</div>
                            </div>
                        </div>
                    </Link>
                </div>

                {/* Features Section */}
                <div className="mt-20 pt-12 border-t border-slate-700/30">
                    <h3 className="text-2xl font-bold mb-8 text-center">Features</h3>
                    <div className="grid md:grid-cols-3 gap-8 max-w-4xl mx-auto">
                        <div className="text-center">
                            <div className="w-12 h-12 rounded-full bg-blue-500/20 flex items-center justify-center mx-auto mb-4">
                                <MessageSquare className="w-6 h-6 text-blue-400" />
                            </div>
                            <h4 className="font-semibold mb-2">AI Chat</h4>
                            <p className="text-sm opacity-60">Ask questions and get instant answers about your videos</p>
                        </div>
                        <div className="text-center">
                            <div className="w-12 h-12 rounded-full bg-purple-500/20 flex items-center justify-center mx-auto mb-4">
                                <Scissors className="w-6 h-6 text-purple-400" />
                            </div>
                            <h4 className="font-semibold mb-2">Auto Highlights</h4>
                            <p className="text-sm opacity-60">Automatically extract key moments and create clips</p>
                        </div>
                        <div className="text-center">
                            <div className="w-12 h-12 rounded-full bg-pink-500/20 flex items-center justify-center mx-auto mb-4">
                                <Video className="w-6 h-6 text-pink-400" />
                            </div>
                            <h4 className="font-semibold mb-2">Video Library</h4>
                            <p className="text-sm opacity-60">Manage and organize all your videos in one place</p>
                        </div>
                    </div>
                </div>
            </main>

            {/* Footer */}
            <footer className={cn('border-t', isDark ? 'border-slate-700/30 bg-slate-900/20' : 'border-slate-200/30 bg-white/20', 'mt-20')}>
                <div className="max-w-7xl mx-auto px-8 py-8 text-center text-sm opacity-50">
                    <p>Video Vault • Powered by AI • v1.0.0</p>
                </div>
            </footer>
        </div>
    );
}
