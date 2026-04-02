import React, { useState } from 'react';
import { Settings, Scissors, Users, Play, GripVertical, Wand2, Clock, Check } from 'lucide-react';

interface ClipOptionsCardProps {
  totalMentions: number;
  onGenerate: (options: { quantity: number; grouping: boolean; style: string }) => void;
  isGenerating?: boolean;
}

export function ClipOptionsCard({ totalMentions, onGenerate, isGenerating = false }: ClipOptionsCardProps) {
  const [quantity, setQuantity] = useState<number>(Math.min(5, totalMentions));
  const [grouping, setGrouping] = useState<boolean>(true);
  const [style, setStyle] = useState<string>('ai_director');

  const styles = [
    {
      id: 'ai_director',
      name: 'Viral AI Director',
      description: 'AI finds the best narrative hook and conclusion',
      icon: <Wand2 className="w-4 h-4" />
    },
    {
      id: 'semantic',
      name: 'Semantic Content',
      description: 'Snaps to natural sentence boundaries',
      icon: <Check className="w-4 h-4" />
    },
    {
      id: 'fixed',
      name: 'Fixed Duration',
      description: 'Strict 5-second context blocks',
      icon: <Clock className="w-4 h-4" />
    }
  ];

  const handleGenerate = () => {
    onGenerate({ quantity, grouping, style });
  };

  return (
    <div className="bg-slate-900 border border-slate-700/50 rounded-lg overflow-hidden my-4 max-w-md w-full animate-fade-in shadow-xl shadow-blue-900/10">
      <div className="bg-gradient-to-r from-blue-900/40 to-indigo-900/40 px-4 py-3 border-b border-slate-700/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Settings className="w-5 h-5 text-blue-400" />
          <h3 className="font-semibold text-slate-200">Clip Generation Settings</h3>
        </div>
        <div className="text-xs bg-blue-500/20 text-blue-300 px-2 py-1 rounded border border-blue-500/30 font-medium">
          {totalMentions} Mentions Found
        </div>
      </div>

      <div className="p-4 space-y-5">
        {/* Quantity control */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1">
            <Scissors className="w-3 h-3" /> Quantity to Make
          </label>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min="1"
              max={totalMentions}
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
              className="flex-1 accent-blue-500"
              disabled={isGenerating}
            />
            <div className="bg-slate-800 text-blue-300 font-mono px-3 py-1 rounded border border-slate-700 min-w-12 text-center text-sm font-semibold">
              {quantity}
            </div>
          </div>
        </div>

        {/* Grouping Toggle */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1">
            <Users className="w-3 h-3" /> Mention Grouping
          </label>
          <button
            onClick={() => !isGenerating && setGrouping(!grouping)}
            disabled={isGenerating}
            className={`w-full flex items-center justify-between p-3 rounded border transition-all ${
              grouping 
                ? 'bg-blue-500/10 border-blue-500/30 text-blue-300' 
                : 'bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-700/50'
            }`}
          >
            <div className="flex items-center gap-2 text-sm font-medium">
              <GripVertical className="w-4 h-4 opacity-50" />
              Group nearby mentions into single clips
            </div>
            <div className={`w-8 h-4 rounded-full transition-colors relative ${grouping ? 'bg-blue-500' : 'bg-slate-600'}`}>
              <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${grouping ? 'left-4.5 right-0.5' : 'left-0.5'}`} style={{ left: grouping ? 'calc(100% - 14px)' : '2px' }} />
            </div>
          </button>
        </div>

        {/* Style Selection */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1">
            <Wand2 className="w-3 h-3" /> Editing Style
          </label>
          <div className="grid grid-cols-1 gap-2">
            {styles.map((s) => (
              <button
                key={s.id}
                onClick={() => !isGenerating && setStyle(s.id)}
                disabled={isGenerating}
                className={`flex items-start gap-3 p-3 rounded border transition-all text-left ${
                  style === s.id
                    ? 'bg-blue-500/10 border-blue-500/50 text-blue-200'
                    : 'bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-700/50'
                }`}
              >
                <div className={`mt-0.5 ${style === s.id ? 'text-blue-400' : 'text-slate-500'}`}>
                  {s.icon}
                </div>
                <div>
                  <div className="text-sm font-semibold">{s.name}</div>
                  <div className={`text-xs mt-1 ${style === s.id ? 'text-blue-300/80' : 'text-slate-500'}`}>
                    {s.description}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Submit */}
        <button
          onClick={handleGenerate}
          disabled={isGenerating}
          className={`w-full flex items-center justify-center gap-2 py-3 rounded font-medium text-sm transition-all ${
            isGenerating 
              ? 'bg-blue-500/50 text-white cursor-not-allowed border border-blue-500/30'
              : 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-500/20'
          }`}
        >
          {isGenerating ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Generating Clips...
            </>
          ) : (
            <>
              <Play className="w-4 h-4" fill="currentColor" />
              Generate {quantity} Clip{quantity !== 1 ? 's' : ''}
            </>
          )}
        </button>
      </div>
    </div>
  );
}
