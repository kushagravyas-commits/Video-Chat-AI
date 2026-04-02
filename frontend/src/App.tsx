import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import HomePage from './pages/HomePage';
import ChatbotPage from './pages/ChatbotPage';
import VideosPage from './pages/VideosPage';
import ClipsPage from './pages/ClipsPage';
import TrashPage from './pages/TrashPage';
import ToolsPage from './pages/ToolsPage';

export default function App() {
    return (
        <Router>
            <Routes>
                <Route path="/" element={<HomePage />} />
                <Route path="/chatbot" element={<ChatbotPage />} />
                <Route path="/videos" element={<VideosPage />} />
                <Route path="/clips" element={<ClipsPage />} />
                <Route path="/trash" element={<TrashPage />} />
                <Route path="/tools" element={<ToolsPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </Router>
    );
}
