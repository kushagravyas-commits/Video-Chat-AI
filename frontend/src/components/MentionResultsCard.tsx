import React from 'react';
import { Clock, Zap, Eye } from 'lucide-react';

export interface Mention {
  timestamp: string;
  text: string;
  confidence: number;
}

export interface MentionResult {
  search_query: string;
  video_title: string;
  total_mentions: number;
  mentions: Mention[];
  time_distribution: {
    [key: string]: number;
  };
  average_confidence: number;
}

interface MentionResultsCardProps {
  data: MentionResult;
}

export default function MentionResultsCard({ data }: MentionResultsCardProps) {
  const getConfidenceBadgeColor = (confidence: number) => {
    if (confidence >= 0.9) return 'bg-green-500/20 text-green-300 border-green-500/30';
    if (confidence >= 0.7) return 'bg-blue-500/20 text-blue-300 border-blue-500/30';
    if (confidence >= 0.5) return 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30';
    return 'bg-red-500/20 text-red-300 border-red-500/30';
  };

  const maxDistributionCount = data.time_distribution
    ? Math.max(0, ...Object.values(data.time_distribution))
    : 0;

  const formatTimestamp = (ts: string) => {
    const match = ts.match(/(\d+):(\d+)/);
    if (match) {
      return `${match[1]}:${match[2].padStart(2, '0')}`;
    }
    return ts;
  };

  return (
    <div className="my-4 space-y-4">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 border border-blue-500/30 rounded-lg p-4">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="text-lg font-bold text-white mb-1">
              Mentions of "{data.search_query}"
            </h3>
            <p className="text-sm text-slate-400">{data.video_title}</p>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold text-blue-400">{data.total_mentions}</div>
            <div className="text-xs text-slate-400">total mentions</div>
          </div>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-2 gap-4 pt-3 border-t border-slate-700/50">
          <div>
            <div className="flex items-center gap-2 text-slate-300 text-sm mb-1">
              <Zap className="w-4 h-4" />
              Confidence
            </div>
            <div className="text-xl font-semibold text-slate-200">
              {(data.average_confidence * 100).toFixed(0)}%
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2 text-slate-300 text-sm mb-2">
              <Clock className="w-4 h-4" />
              Distribution
            </div>
            <div className="space-y-2 text-xs text-slate-300 max-h-32 overflow-y-auto pr-2 scrollbar-thin">
              {Object.entries(data.time_distribution || {}).map(([range, count]) => {
                const width = maxDistributionCount > 0 ? `${(count / maxDistributionCount) * 100}%` : '0%';
                return (
                  <div key={range} className="flex items-center gap-2 group">
                    <div className="w-20 truncate text-right opacity-80" title={range}>{range}</div>
                    <div className="flex-1 h-3 bg-slate-900/50 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 rounded-full transition-all duration-500 group-hover:bg-blue-400" style={{ width }} />
                    </div>
                    <div className="w-4 text-right font-semibold text-blue-300">{count}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Mentions List */}
      <div className="space-y-2">
        <h4 className="text-sm font-semibold text-slate-400 px-1">Mentions Timeline</h4>
        {data.mentions.map((mention, idx) => (
          <div
            key={idx}
            className="bg-slate-800/40 border border-slate-700/50 rounded-lg p-3 hover:border-slate-600/50 transition-colors"
          >
            <div className="flex items-start justify-between gap-3 mb-2">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-500/20 text-blue-300 text-xs font-bold">
                  {idx + 1}
                </span>
                <span className="font-mono text-sm font-semibold text-blue-400">
                  {formatTimestamp(mention.timestamp)}
                </span>
              </div>
              <div
                className={`px-2 py-1 rounded text-xs font-semibold border ${getConfidenceBadgeColor(
                  mention.confidence
                )}`}
              >
                {(mention.confidence * 100).toFixed(0)}%
              </div>
            </div>
            <p className="text-sm text-slate-300 leading-relaxed pl-8 italic">
              "{mention.text}"
            </p>
          </div>
        ))}
      </div>

      {/* Action Suggestion */}
      <div className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-3 mt-4">
        <div className="flex items-center gap-2 text-sm text-slate-300">
          <Eye className="w-4 h-4 flex-shrink-0" />
          <span>
            Would you like me to create video clips for any of these mentions?
          </span>
        </div>
      </div>
    </div>
  );
}
