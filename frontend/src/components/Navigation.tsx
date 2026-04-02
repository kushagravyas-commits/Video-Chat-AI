import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Video, MessageSquare, Film, Scissors, Wrench, Home, Trash2 } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

export default function Navigation() {
    const location = useLocation();

    const navLinks = [
        { path: '/', label: 'Home', icon: Home },
        { path: '/chatbot', label: 'Chatbot', icon: MessageSquare },
        { path: '/videos', label: 'Videos', icon: Film },
        { path: '/clips', label: 'Clips', icon: Scissors },
        { path: '/trash', label: 'Trash', icon: Trash2 },
        { path: '/tools', label: 'Tools', icon: Wrench },
    ];

    const isActive = (path: string) => location.pathname === path;

    return (
        <nav className="bg-gradient-to-r from-slate-900 to-slate-800 border-b border-slate-700/30 backdrop-blur-md sticky top-0 z-40">
            <div className="max-w-7xl mx-auto px-8 py-4">
                <div className="flex items-center justify-between">
                    {/* Logo */}
                    <Link to="/" className="flex items-center gap-2 font-bold text-xl group">
                        <div className="p-2 rounded-lg bg-blue-500/20 group-hover:bg-blue-500/30 transition-colors">
                            <Video className="w-5 h-5 text-blue-400" />
                        </div>
                        <span className="text-slate-200">Video Vault</span>
                    </Link>

                    {/* Nav Links */}
                    <div className="flex items-center gap-2">
                        {navLinks.map(({ path, label, icon: Icon }) => (
                            <Link
                                key={path}
                                to={path}
                                className={cn(
                                    'px-4 py-2 rounded-lg transition-all flex items-center gap-2 font-medium text-sm',
                                    isActive(path)
                                        ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/30'
                                )}
                            >
                                <Icon className="w-4 h-4" />
                                {label}
                            </Link>
                        ))}
                    </div>

                    {/* Right Side */}
                    <div className="flex items-center gap-3">
                        <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                        <span className="text-xs text-slate-400">Online</span>
                    </div>
                </div>
            </div>
        </nav>
    );
}
