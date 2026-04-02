import React, { useState, useEffect } from 'react';
import { Scissors, Play, X, Trash2 } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import Navigation from '../components/Navigation';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

interface Clip {
    id: number;
    title: string;
    duration: string;
    created: string;
    videoId: string;
    youtubeUrl: string;
    isLocal?: boolean;
}

export default function ClipsPage() {
    const [clips, setClips] = useState<Clip[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedClip, setSelectedClip] = useState<Clip | null>(null);
    const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

    useEffect(() => {
        loadClips();
    }, []);

    const loadClips = () => {
        fetch('/api/clips')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success' && data.clips) {
                    setClips(data.clips);
                }
                setLoading(false);
            })
            .catch(err => {
                console.error('Error fetching clips:', err);
                setLoading(false);
            });
    };

    const handleDeleteClip = async (clipId: number) => {
        const clip = clips.find(c => c.id === clipId);
        if (!clip) return;

        try {
            // Extract clip filename from the clip title/id
            const clipFilename = clip.videoId.replace('clip-', '') + '.mp4';
            const response = await fetch(`/api/clips/${clip.videoId.replace('clip-', '')}/delete`, {
                method: 'POST'
            });
            const data = await response.json();
            if (data.status === 'success') {
                alert('Clip moved to trash');
                loadClips();
                setSelectedClip(null);
                setConfirmDelete(null);
            } else {
                alert('Error: ' + (data.message || 'Failed to delete'));
            }
        } catch (error) {
            console.error('Error deleting clip:', error);
            alert('Error deleting clip');
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
                            <div className="p-3 rounded-lg bg-pink-500/20">
                                <Scissors className="w-8 h-8 text-pink-400" />
                            </div>
                            <div>
                                <h1 className="text-4xl font-bold">Clips Store</h1>
                                <p className="text-sm opacity-60 mt-2">All your generated highlights and clips</p>
                            </div>
                        </div>
                    </div>

                    {/* Clips Grid */}
                    {loading ? (
                        <div className="text-center py-12">
                            <div className="w-8 h-8 rounded-full border-2 border-pink-500/30 border-t-pink-500 animate-spin mx-auto"></div>
                            <p className="mt-4 opacity-60">Loading clips...</p>
                        </div>
                    ) : clips.length === 0 ? (
                        <div className={cn('text-center py-16 rounded-2xl', isDark ? 'bg-slate-800/30' : 'bg-slate-200/30', 'border', isDark ? 'border-slate-700/30' : 'border-slate-200/30')}>
                            <Scissors className="w-16 h-16 mx-auto opacity-30 mb-4" />
                            <h3 className="text-xl font-semibold mb-2">No clips yet</h3>
                            <p className="opacity-60 mb-6">Start by creating highlights in the chatbot</p>
                            <a
                                href="/chatbot"
                                className="inline-block px-6 py-2 rounded-lg bg-pink-500 text-white font-semibold hover:bg-pink-600 transition-colors"
                            >
                                Create Highlights →
                            </a>
                        </div>
                    ) : (
                        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {clips.map((clip) => (
                                <div
                                    key={clip.id}
                                    className={cn(
                                        'group text-left rounded-xl overflow-hidden transition-all',
                                        isDark ? 'bg-slate-800/30 border border-slate-700/30 hover:border-pink-500/30' : 'bg-slate-200/30 border border-slate-200/30 hover:border-pink-200/30'
                                    )}
                                >
                                    <button
                                        onClick={() => setSelectedClip(clip)}
                                        className="w-full hover:scale-105 transition-transform"
                                    >
                                        <div className={cn('p-4 h-40 flex items-center justify-center', isDark ? 'bg-slate-900/50' : 'bg-slate-300/20')}>
                                            <div className="w-12 h-12 rounded-full bg-pink-500/20 flex items-center justify-center group-hover:bg-pink-500/30 transition-colors">
                                                <Play className="w-6 h-6 text-pink-400 fill-current ml-0.5" />
                                            </div>
                                        </div>
                                        <div className="p-4">
                                            <h3 className="font-bold text-sm mb-2 line-clamp-2">{clip.title}</h3>
                                            <div className="flex items-center justify-between text-xs opacity-60">
                                                <span>{clip.duration}</span>
                                                <span>{clip.created}</span>
                                            </div>
                                        </div>
                                    </button>
                                    <div className="px-4 pb-4 border-t border-slate-700/30">
                                        <button
                                            onClick={() => setConfirmDelete(clip.id)}
                                            className="w-full px-3 py-2 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors flex items-center justify-center gap-2 text-sm font-medium"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                            Delete
                                        </button>
                                    </div>

                                    {/* Confirmation Dialog */}
                                    {confirmDelete === clip.id && (
                                        <div className="absolute inset-0 bg-black/70 rounded-xl flex items-center justify-center p-4 z-10">
                                            <div className="bg-slate-900 p-4 rounded-lg text-center">
                                                <p className="text-white mb-4 font-semibold">Move to trash?</p>
                                                <div className="flex gap-2 justify-center">
                                                    <button
                                                        onClick={() => {
                                                            handleDeleteClip(clip.id);
                                                        }}
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
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </main>

            {/* Clip Player Modal */}
            {selectedClip && (
                <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setSelectedClip(null)}>
                    <div className="bg-slate-900/90 rounded-2xl p-6 max-w-2xl w-full" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-xl font-bold">{selectedClip.title}</h3>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => setConfirmDelete(selectedClip.id)}
                                    className="p-2 hover:bg-red-800 rounded-lg transition-colors text-red-400"
                                >
                                    <Trash2 className="w-5 h-5" />
                                </button>
                                <button
                                    onClick={() => setSelectedClip(null)}
                                    className="p-2 hover:bg-slate-800 rounded-lg transition-colors"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                        </div>

                        {/* Confirmation Dialog */}
                        {confirmDelete === selectedClip.id && (
                            <div className="mb-4 p-4 bg-red-900/30 border border-red-600 rounded-lg">
                                <p className="text-white mb-3">Move this clip to trash?</p>
                                <div className="flex gap-3">
                                    <button
                                        onClick={() => handleDeleteClip(selectedClip.id)}
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

                        {/* Video Player */}
                        <div className="relative w-full bg-black rounded-lg overflow-hidden mb-4">
                            <div className="aspect-video flex items-center justify-center bg-gradient-to-br from-pink-900/40 via-slate-900/20 to-purple-900/40">
                                {selectedClip.isLocal ? (
                                    // Local video player
                                    <video
                                        width="100%"
                                        height="100%"
                                        controls
                                        autoPlay
                                        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                                    >
                                        <source src={selectedClip.youtubeUrl} type="video/mp4" />
                                        Your browser does not support the video tag.
                                    </video>
                                ) : (
                                    // YouTube iframe player
                                    <iframe
                                        width="100%"
                                        height="100%"
                                        src={`https://www.youtube.com/embed/${extractYoutubeId(selectedClip.youtubeUrl)}?autoplay=1`}
                                        title={selectedClip.title}
                                        frameBorder="0"
                                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                                        allowFullScreen
                                        style={{ position: 'absolute', top: 0, left: 0 }}
                                    />
                                )}
                            </div>
                        </div>

                        {/* Details */}
                        <div className="space-y-2">
                            <div className="flex items-center justify-between text-sm opacity-75">
                                <span>Duration: {selectedClip.duration}</span>
                                <span>Created: {selectedClip.created}</span>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function extractYoutubeId(url: string): string {
    const match = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)/);
    return match ? match[1] : '';
}
