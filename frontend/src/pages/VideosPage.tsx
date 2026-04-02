import React, { useState, useEffect } from 'react';
import { Film, Link as LinkIcon, Trash2 } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import Navigation from '../components/Navigation';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

interface VideoEntry {
    id: string;
    title: string;
    channel?: string;
    url?: string;
    published_at?: string;
    processed_at?: string;
}

const formatDate = (dateStr: string | undefined): string => {
    if (!dateStr) return 'Unknown';
    // Handle YYYYMMDD format
    if (dateStr.length === 8 && /^\d+$/.test(dateStr)) {
        return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6)}`;
    }
    const date = new Date(dateStr);
    return isNaN(date.getTime()) ? dateStr : date.toLocaleDateString();
};

export default function VideosPage() {
    const [videos, setVideos] = useState<VideoEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

    useEffect(() => {
        loadVideos();
    }, []);

    const loadVideos = () => {
        fetch('/api/videos')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    setVideos(data.videos);
                }
                setLoading(false);
            })
            .catch(err => {
                console.error('Error fetching videos:', err);
                setLoading(false);
            });
    };

    const handleDeleteVideo = async (videoId: string) => {
        try {
            const response = await fetch(`/api/videos/${videoId}/delete`, { method: 'POST' });
            const data = await response.json();
            if (data.status === 'success') {
                alert('Video moved to trash');
                loadVideos();
                setConfirmDelete(null);
            } else {
                alert('Error: ' + (data.message || 'Failed to delete'));
            }
        } catch (error) {
            console.error('Error deleting video:', error);
            alert('Error deleting video');
        }
    };

    const isDark = true;

    return (
        <div className={cn('flex flex-col h-screen', isDark ? 'bg-slate-950' : 'bg-slate-50', isDark ? 'text-slate-200' : 'text-slate-800')}>
            <Navigation />

            <main className="flex-1 overflow-y-auto p-8">
                <div className="max-w-6xl mx-auto">
                    {/* Header */}
                    <div className="mb-12">
                        <div className="flex items-center gap-4 mb-4">
                            <div className="p-3 rounded-lg bg-blue-500/20">
                                <Film className="w-8 h-8 text-blue-400" />
                            </div>
                            <div>
                                <h1 className="text-4xl font-bold">Videos Store</h1>
                                <p className="text-sm opacity-60 mt-2">Browse all your processed videos</p>
                            </div>
                        </div>
                    </div>

                    {/* Videos Grid */}
                    {loading ? (
                        <div className="text-center py-12">
                            <div className="w-8 h-8 rounded-full border-2 border-blue-500/30 border-t-blue-500 animate-spin mx-auto"></div>
                            <p className="mt-4 opacity-60">Loading videos...</p>
                        </div>
                    ) : videos.length === 0 ? (
                        <div className={cn('text-center py-16 rounded-2xl', isDark ? 'bg-slate-800/30' : 'bg-slate-200/30', 'border', isDark ? 'border-slate-700/30' : 'border-slate-200/30')}>
                            <Film className="w-16 h-16 mx-auto opacity-30 mb-4" />
                            <h3 className="text-xl font-semibold mb-2">No videos yet</h3>
                            <p className="opacity-60 mb-6">Start by processing a YouTube video in the chatbot</p>
                            <a
                                href="/chatbot"
                                className="inline-block px-6 py-2 rounded-lg bg-blue-500 text-white font-semibold hover:bg-blue-600 transition-colors"
                            >
                                Go to Chatbot →
                            </a>
                        </div>
                    ) : (
                        <div className="grid gap-6">
                            {videos.map((video, idx) => (
                                <div
                                    key={video.id}
                                    className={cn(
                                        'p-6 rounded-xl transition-all hover:scale-102 flex flex-col',
                                        isDark ? 'bg-slate-800/30 border border-slate-700/30 hover:border-blue-500/30' : 'bg-slate-200/30 border border-slate-200/30 hover:border-blue-200/30'
                                    )}
                                >
                                    <div className="flex items-start gap-4">
                                        <div className="p-3 rounded-lg bg-blue-500/20 shrink-0">
                                            <Film className="w-6 h-6 text-blue-400" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <h3 className="text-xl font-bold mb-2 truncate" title={video.title}>{video.title || `Video ${idx + 1}`}</h3>

                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-y-2 gap-x-6 mt-3">
                                                <div className="text-sm">
                                                    <span className="opacity-60">ID:</span> <span className="font-mono ml-1">{video.id}</span>
                                                </div>

                                                {video.channel && (
                                                    <div className="text-sm truncate" title={video.channel}>
                                                        <span className="opacity-60">Channel:</span> <span className="font-medium ml-1">{video.channel}</span>
                                                    </div>
                                                )}

                                                {video.published_at && (
                                                    <div className="text-sm">
                                                        <span className="opacity-60">Published:</span> <span className="ml-1">{formatDate(video.published_at)}</span>
                                                    </div>
                                                )}

                                                {video.processed_at && (
                                                    <div className="text-sm">
                                                        <span className="opacity-60">Processed:</span> <span className="ml-1">{formatDate(video.processed_at)}</span>
                                                    </div>
                                                )}
                                            </div>

                                            {video.url && (
                                                <div className="flex items-center gap-2 mt-4 bg-black/20 p-2 rounded-md">
                                                    <LinkIcon className="w-4 h-4 text-blue-400 shrink-0" />
                                                    <a
                                                        href={video.url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-blue-400 hover:text-blue-300 text-sm truncate"
                                                        title={video.url}
                                                    >
                                                        {video.url}
                                                    </a>
                                                </div>
                                            )}
                                        </div>
                                        <div className="flex gap-2 shrink-0 mt-1">
                                            <a
                                                href={`/chatbot?video=${video.id}`}
                                                className="px-4 py-2 rounded-lg bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 transition-colors"
                                            >
                                                Chat
                                            </a>
                                            <button
                                                onClick={() => setConfirmDelete(video.id)}
                                                className="px-4 py-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors flex items-center gap-2"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                                Delete
                                            </button>
                                        </div>
                                    </div>

                                    {/* Confirmation Dialog */}
                                    {confirmDelete === video.id && (
                                        <div className="mt-4 p-4 bg-red-900/30 border border-red-600 rounded-lg">
                                            <p className="text-white mb-3">
                                                Delete this video? It will be moved to trash and can be recovered within 10 days.
                                            </p>
                                            <div className="flex gap-3">
                                                <button
                                                    onClick={() => handleDeleteVideo(video.id)}
                                                    className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded transition-colors"
                                                >
                                                    Delete
                                                </button>
                                                <button
                                                    onClick={() => setConfirmDelete(null)}
                                                    className="px-4 py-2 bg-slate-600 hover:bg-slate-700 text-white rounded transition-colors"
                                                >
                                                    Cancel
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
