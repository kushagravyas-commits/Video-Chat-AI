import React, { useState, useEffect } from 'react';
import { Trash2, RotateCcw, AlertTriangle, Calendar } from 'lucide-react';
import Navigation from '../components/Navigation';

interface TrashVideo {
  id: string;
  title: string;
  deleted_at: string;
  days_remaining: number;
  is_expired: boolean;
  channel?: string;
}

interface TrashClip {
  filename: string;
  clip_id: string;
  deleted_at: string;
  days_remaining: number;
  is_expired: boolean;
}

export default function TrashPage() {
  const [videos, setVideos] = useState<TrashVideo[]>([]);
  const [clips, setClips] = useState<TrashClip[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTab, setSelectedTab] = useState<'videos' | 'clips'>('videos');
  const [confirmDelete, setConfirmDelete] = useState<{ type: 'video' | 'clip'; id: string } | null>(null);

  useEffect(() => {
    loadTrash();
  }, []);

  const loadTrash = async () => {
    try {
      const response = await fetch('/api/trash');
      const data = await response.json();
      if (data.status === 'success') {
        setVideos(data.videos || []);
        setClips(data.clips || []);
      }
    } catch (error) {
      console.error('Error loading trash:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRecover = async (type: 'video' | 'clip', id: string) => {
    try {
      const endpoint =
        type === 'video' ? `/api/trash/videos/${id}/recover` : `/api/trash/clips/${id}/recover`;
      const response = await fetch(endpoint, { method: 'POST' });
      const data = await response.json();

      if (data.status === 'success') {
        // Reload trash
        loadTrash();
        alert(`${type === 'video' ? 'Video' : 'Clip'} recovered successfully!`);
      } else {
        alert(`Error: ${data.message || 'Failed to recover'}`);
      }
    } catch (error) {
      console.error('Error recovering:', error);
      alert('Error recovering item');
    }
  };

  const handlePermanentDelete = async (type: 'video' | 'clip', id: string) => {
    try {
      const endpoint =
        type === 'video' ? `/api/trash/videos/${id}` : `/api/trash/clips/${id}`;
      const response = await fetch(endpoint, { method: 'DELETE' });
      const data = await response.json();

      if (data.status === 'success') {
        // Reload trash
        loadTrash();
        setConfirmDelete(null);
        alert(`${type === 'video' ? 'Video' : 'Clip'} permanently deleted!`);
      } else {
        alert(`Error: ${data.message || 'Failed to delete'}`);
      }
    } catch (error) {
      console.error('Error deleting:', error);
      alert('Error deleting item');
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const isExpired = (days: number) => days <= 0;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <Navigation />

      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <Trash2 className="w-8 h-8 text-red-500" />
            <h1 className="text-4xl font-bold text-white">Trash</h1>
          </div>
          <p className="text-slate-400">
            Deleted items are kept for 10 days. After that, they are permanently deleted.
          </p>
        </div>

        {/* Tabs */}
        <div className="flex gap-4 mb-8 border-b border-slate-700">
          <button
            onClick={() => setSelectedTab('videos')}
            className={`pb-4 px-4 font-semibold transition-colors ${
              selectedTab === 'videos'
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            Deleted Videos ({videos.length})
          </button>
          <button
            onClick={() => setSelectedTab('clips')}
            className={`pb-4 px-4 font-semibold transition-colors ${
              selectedTab === 'clips'
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            Deleted Clips ({clips.length})
          </button>
        </div>

        {/* Videos Tab */}
        {selectedTab === 'videos' && (
          <div className="space-y-4">
            {loading ? (
              <div className="text-center py-8 text-slate-400">Loading...</div>
            ) : videos.length === 0 ? (
              <div className="text-center py-12 text-slate-400">
                <Trash2 className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>No deleted videos</p>
              </div>
            ) : (
              videos.map((video) => (
                <div
                  key={video.id}
                  className={`p-6 rounded-lg border transition-all ${
                    isExpired(video.days_remaining)
                      ? 'bg-red-900/20 border-red-600/30'
                      : 'bg-slate-800/50 border-slate-700'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h3 className="text-xl font-semibold text-white mb-2">{video.title}</h3>
                      {video.channel && <p className="text-slate-400 mb-2">{video.channel}</p>}

                      <div className="flex items-center gap-4 text-sm text-slate-400">
                        <div className="flex items-center gap-2">
                          <Calendar className="w-4 h-4" />
                          Deleted: {formatDate(video.deleted_at)}
                        </div>

                        {isExpired(video.days_remaining) ? (
                          <div className="flex items-center gap-2 text-red-400">
                            <AlertTriangle className="w-4 h-4" />
                            Expired
                          </div>
                        ) : (
                          <div className="text-slate-300 font-semibold">
                            {video.days_remaining} day{video.days_remaining !== 1 ? 's' : ''} remaining
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex gap-3 ml-4">
                      {!isExpired(video.days_remaining) && (
                        <button
                          onClick={() => handleRecover('video', video.id)}
                          className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg flex items-center gap-2 transition-colors"
                        >
                          <RotateCcw className="w-4 h-4" />
                          Recover
                        </button>
                      )}
                      <button
                        onClick={() => setConfirmDelete({ type: 'video', id: video.id })}
                        className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg flex items-center gap-2 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                        Delete
                      </button>
                    </div>
                  </div>

                  {/* Confirmation Dialog */}
                  {confirmDelete?.type === 'video' && confirmDelete?.id === video.id && (
                    <div className="mt-4 p-4 bg-red-900/30 border border-red-600 rounded-lg">
                      <p className="text-white mb-3">
                        Permanently delete this video? This action cannot be undone.
                      </p>
                      <div className="flex gap-3">
                        <button
                          onClick={() => handlePermanentDelete('video', video.id)}
                          className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded transition-colors"
                        >
                          Yes, Delete Permanently
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
              ))
            )}
          </div>
        )}

        {/* Clips Tab */}
        {selectedTab === 'clips' && (
          <div className="space-y-4">
            {loading ? (
              <div className="text-center py-8 text-slate-400">Loading...</div>
            ) : clips.length === 0 ? (
              <div className="text-center py-12 text-slate-400">
                <Trash2 className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>No deleted clips</p>
              </div>
            ) : (
              clips.map((clip) => (
                <div
                  key={clip.filename}
                  className={`p-6 rounded-lg border transition-all ${
                    isExpired(clip.days_remaining)
                      ? 'bg-red-900/20 border-red-600/30'
                      : 'bg-slate-800/50 border-slate-700'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h3 className="text-xl font-semibold text-white mb-2">
                        {clip.clip_id.replace(/_/g, ' ')}
                      </h3>
                      <p className="text-slate-400 text-sm mb-3">{clip.filename}</p>

                      <div className="flex items-center gap-4 text-sm text-slate-400">
                        <div className="flex items-center gap-2">
                          <Calendar className="w-4 h-4" />
                          Deleted: {formatDate(clip.deleted_at)}
                        </div>

                        {isExpired(clip.days_remaining) ? (
                          <div className="flex items-center gap-2 text-red-400">
                            <AlertTriangle className="w-4 h-4" />
                            Expired
                          </div>
                        ) : (
                          <div className="text-slate-300 font-semibold">
                            {clip.days_remaining} day{clip.days_remaining !== 1 ? 's' : ''} remaining
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex gap-3 ml-4">
                      {!isExpired(clip.days_remaining) && (
                        <button
                          onClick={() => handleRecover('clip', clip.filename)}
                          className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg flex items-center gap-2 transition-colors"
                        >
                          <RotateCcw className="w-4 h-4" />
                          Recover
                        </button>
                      )}
                      <button
                        onClick={() => setConfirmDelete({ type: 'clip', id: clip.filename })}
                        className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg flex items-center gap-2 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                        Delete
                      </button>
                    </div>
                  </div>

                  {/* Confirmation Dialog */}
                  {confirmDelete?.type === 'clip' && confirmDelete?.id === clip.filename && (
                    <div className="mt-4 p-4 bg-red-900/30 border border-red-600 rounded-lg">
                      <p className="text-white mb-3">
                        Permanently delete this clip? This action cannot be undone.
                      </p>
                      <div className="flex gap-3">
                        <button
                          onClick={() => handlePermanentDelete('clip', clip.filename)}
                          className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded transition-colors"
                        >
                          Yes, Delete Permanently
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
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
