'use client';

import { useState, useEffect, useRef } from 'react';
import { BACKEND_URL } from '@/config'; 
import NodeDetailModal from '@/components/modals/NodeDetailModal';
import LocalSyncButton from '@/components/sync/LocalSyncButton';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Types
interface ReferencedNode {
  id: string;
  title: string;
  similarity: string;
}

interface ChatMessage {
  role: 'user' | 'ai';
  text: string;
  activeMode?: 'general' | 'project'; 
  references?: ReferencedNode[];
}

export default function CosmosWikiDashboard() {
  const [message, setMessage] = useState('');
  
  // State
  const [activeMode, setActiveMode] = useState<'general' | 'project'>('general');
  const [activeFile, setActiveFile] = useState<{ id: string; path: string } | null>(null);
  const [blueprints, setBlueprints] = useState<{ id: string; path: string }[]>([]);

  const [chatLog, setChatLog] = useState<ChatMessage[]>([
    { role: 'ai', text: '안녕하세요. CosmosWiki AI입니다.' },
  ]);
  const [isThinking, setIsThinking] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const [liveFeeds, setLiveFeeds] = useState<{ id: string; title: string; content: string; created_at: string }[]>([]);
  const [isLoadingFeed, setIsLoadingFeed] = useState(false);

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const [mounted, setMounted] = useState(false);

  // Load live feeds
  const fetchLiveFeeds = async () => {
    setIsLoadingFeed(true);
    try {
      const res = await fetch(`${BACKEND_URL}/wiki/nodes/gemini`); 
      if (res.ok) {
        const data = await res.json();
        setLiveFeeds(data.nodes || data || []);
      }
    } catch (err) {
      console.error('Failed to load live feeds:', err);
    } finally {
      setIsLoadingFeed(false);
    }
  };

  // Load blueprint list
  const fetchBlueprints = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/project/blueprints`);
      if (res.ok) {
        const data = await res.json();
        setBlueprints(data.blueprints || data || []);
      }
    } catch (err) {
      console.error('Failed to load blueprints:', err);
    }
  };

  const scrollToBottom = () => {
    setTimeout(() => {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, 50);
  };

  useEffect(() => {
    fetchLiveFeeds();
    fetchBlueprints();
  }, []);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [chatLog]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim()) return;

    const userMessage = message;
    const currentMode = activeMode; 
    const currentFile = activeFile; 

    setChatLog((prev) => [...prev, { role: 'user', text: userMessage }]);
    setMessage('');
    setIsThinking(true);

    try {
      const res = await fetch(`${BACKEND_URL}/chat/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: userMessage,
          mode: currentMode, 
          session_id: 'session_default',
          active_file: currentFile ? {
            id: currentFile.id,
            path: currentFile.path
          } : null
        }),
      });
      const data = await res.json();

      if (res.ok) {
        setChatLog((prev) => [
          ...prev, 
          { 
            role: 'ai', 
            text: data.ai_response,
            activeMode: currentMode,
            references: data.references || [] 
          }
        ]);
        fetchLiveFeeds();
      } else {
        setChatLog((prev) => [...prev, { role: 'ai', text: `요청 처리 중 오류가 발생했습니다. (${data.detail})` }]);
      }
    } catch {
      setChatLog((prev) => [...prev, { role: 'ai', text: '서버 연결에 실패했습니다.' }]);
    } finally {
      setIsThinking(false);
    }
  };

  const handleSaveToKnowledgeBase = async (rawText: string) => {
    try {
      const response = await fetch(`${BACKEND_URL}/wiki/save-chat-node`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text: rawText }),
      });

      if (!response.ok) throw new Error('Network error');

      alert('지식 저장 요청이 접수되었습니다.');
    } catch (error) {
      console.error('Failed to save knowledge:', error);
      alert('요청 처리 중 오류가 발생했습니다.');
    }
  };

  const handleNodeClick = (nodeId: string) => {
    setSelectedNodeId(nodeId);
    setIsModalOpen(true);
  };

  return (
    <div className="h-screen w-full bg-[#fafafa] text-[#111111] font-sans p-8 pt-30 pb-6 flex flex-col justify-between selection:bg-neutral-900 selection:text-white overflow-hidden">
      
      <main className="max-w-7xl w-full mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 h-[calc(100vh-160px)] pb-2 items-stretch">
        
        {/* Left panel: Chat and retrieval */}
        <section className="lg:col-span-8 bg-white border border-neutral-100 rounded-2xl p-7 flex flex-col justify-between h-full shadow-[0_8px_30px_rgb(0,0,0,0.04)] backdrop-blur-sm overflow-hidden">
          <div className="flex flex-col h-full justify-between min-h-0">
            <div className="flex flex-col h-full min-h-0">
              
              {/* Header and mode navigation */}
              <div className="flex items-center justify-between border-b border-neutral-100 pb-4 mb-4 flex-shrink-0">
                <div className="flex items-center space-x-2">
                  <span className="text-xs text-neutral-400 font-mono">01 /</span>
                  <h2 className="text-xs font-bold uppercase tracking-widest text-neutral-800">AI Workspace</h2>
                </div>

                {/* Mode controls */}
                <div className="flex bg-neutral-100 p-1 rounded-xl border border-neutral-200/50 scale-90 sm:scale-100 origin-right">
                  <button
                    onClick={() => setActiveMode('general')}
                    className={`px-4 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-tighter transition-all duration-300 ${
                      activeMode === 'general' 
                        ? 'bg-white text-neutral-900 shadow-sm' 
                        : 'text-neutral-400 hover:text-neutral-600'
                    }`}
                  >
                    Cosmos Mode
                  </button>
                  <button
                    onClick={() => setActiveMode('project')}
                    className={`px-4 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-tighter transition-all duration-300 ${
                      activeMode === 'project' 
                        ? 'bg-neutral-900 text-white shadow-md' 
                        : 'text-neutral-400 hover:text-neutral-600'
                    }`}
                  >
                    Code Mode
                  </button>
                </div>
              </div>
              
              <div className="flex-grow overflow-y-auto space-y-5 pr-1 mb-4 scrollbar-thin min-h-0">
                {mounted && chatLog.map((chat, idx) => (
                  <div key={idx} className={`flex flex-col ${chat.role === 'user' ? 'items-end' : 'items-start'}`}>
                    <div className={`group relative max-w-[80%] px-4 py-2.5 text-base leading-relaxed rounded-2xl transition-all duration-350 ease-in-out h-auto ${
                      chat.role === 'user' 
                        ? 'bg-neutral-900 text-white rounded-tr-none' 
                        : 'bg-neutral-100 text-neutral-800 rounded-tl-none hover:bg-neutral-150 shadow-sm prose prose-neutral max-w-none prose-sm prose-p:m-0 prose-headings:text-neutral-900 prose-headings:font-bold prose-headings:my-2'
                    }`}>
                      {chat.role === 'user' ? (
                        <p className="block m-0 p-0 whitespace-pre-wrap">{chat.text}</p>
                      ) : (
                        <ReactMarkdown 
                          remarkPlugins={[remarkGfm]}
                          components={{
                            h2: ({ node: _node, ...props }) => (
                              <h2 className="text-lg font-extrabold text-neutral-900 mt-4 mb-2 tracking-wide block border-b border-neutral-200/60 pb-1 font-mono" {...props} />
                            ),
                            h3: ({ node: _node, ...props }) => (
                              <h3 className="text-base font-bold text-neutral-800 mt-3 mb-1.5 block" {...props} />
                            ),
                            p: ({ node: _node, ...props }) => (
                              <p className="text-sm text-neutral-800 leading-relaxed my-1 block" {...props} />
                            ),
                            ul: ({ node: _node, ...props }) => (
                              <ul className="list-disc pl-5 my-2 text-sm text-neutral-800 space-y-1" {...props} />
                            ),
                            ol: ({ node: _node, ...props }) => (
                              <ol className="list-decimal pl-5 my-2 text-sm text-neutral-800 space-y-1" {...props} />
                            ),
                            li: ({ node: _node, ...props }) => (
                              <li className="text-sm text-neutral-800" {...props} />
                            )
                          }}
                        >
                          {chat.text}
                        </ReactMarkdown>
                      )}

                      {chat.role === 'ai' && (
                        <div className="opacity-0 invisible group-hover:opacity-100 group-hover:visible max-h-0 group-hover:max-h-40 overflow-hidden transition-all duration-300 ease-in-out mt-0 group-hover:mt-4 group-hover:pt-3 group-hover:border-t group-hover:border-neutral-200/60 flex items-end justify-between gap-4 w-full">
                          <div className="flex-grow min-w-0">
                            {chat.references && chat.references.length > 0 ? (
                              <>
                                <div className="text-[10px] font-mono font-bold text-neutral-400 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                                  <span>🔗 RAG Vector References</span>
                                </div>
                                <div className="flex flex-wrap gap-1.5">
                                  {chat.references.slice(0, 3).map((ref) => (
                                    <button
                                      key={ref.id}
                                      onClick={() => handleNodeClick(ref.id)}
                                      className="inline-flex items-center gap-1 text-[11px] font-medium bg-white border border-neutral-200 text-neutral-700 px-2 py-0.5 rounded-md hover:border-neutral-900 hover:text-black transition-all duration-150 cursor-pointer shadow-sm"
                                    >
                                      <span className="max-w-[85px] truncate">{ref.title}</span>
                                      <span className="text-[9px] font-mono font-bold text-neutral-400 bg-neutral-50 px-1 rounded border border-neutral-100">
                                        {ref.similarity}%
                                      </span>
                                    </button>
                                  ))}
                                </div>
                              </>
                            ) : (
                              <div className="text-[10px] font-mono text-neutral-400 italic pl-0.5">
                                No contextual nodes referenced.
                              </div>
                            )}
                          </div>

                          <div className="flex-shrink-0 self-end mb-0.5">
                            <button
                              onClick={() => handleSaveToKnowledgeBase(chat.text)}
                              className="inline-flex items-center gap-1.5 text-[10px] font-mono font-bold uppercase tracking-wider bg-white border border-neutral-200 hover:border-neutral-900 text-neutral-500 hover:text-black px-2.5 py-2.5 rounded-lg transition-all duration-150 cursor-pointer shadow-sm hover:shadow"
                            >
                              <div className="text-neutral-400 text-xs">Save to DB</div>
                            </button>
                          </div>

                        </div>
                      )}
                    </div>
                  </div>
                ))}
                
                {isThinking && (
                  <div className="flex justify-start">
                    <div className="bg-neutral-50 border border-neutral-200/60 text-neutral-400 font-mono text-xs rounded-xl px-4 py-2.5 animate-pulse">
                      {activeMode === 'general' 
                        ? 'Navigating knowledge nodes...' 
                        : 'Analyzing code blueprints...'}
                    </div>
                  </div>
                )}

                <div ref={chatEndRef} />
              </div>
            </div>

            <div className={`transition-all duration-200 flex flex-col flex-shrink-0 ${
              activeMode === 'project' 
                ? 'border border-neutral-400 rounded-xl focus-within:border-neutral-900 focus-within:ring-1 focus-within:ring-neutral-900 overflow-hidden bg-neutral-50' 
                : ''
            }`}>
              
              {activeMode === 'project' && (
                <div className="flex items-center space-x-2 border-b border-neutral-200/80 px-3 h-9 text-xs text-neutral-500 animate-fadeIn flex-shrink-0">
                  <span className="font-mono text-[10px] uppercase bg-neutral-200 text-neutral-700 px-1.5 py-0.5 rounded font-bold">Focus File</span>
                  <select
                    className="bg-transparent border-none text-neutral-800 font-mono focus:outline-none cursor-pointer max-w-[250px] truncate text-xs h-full"
                    value={activeFile?.id || ""}
                    onChange={(e) => {
                      const selected = blueprints.find(bp => bp.id === e.target.value);
                      setActiveFile(selected || null);
                    }}
                  >
                    <option value="">-- 전체 아키텍처 탐색 --</option>
                    {blueprints.map((bp) => (
                      <option key={bp.id} value={bp.id}>{bp.path}</option>
                    ))}
                  </select>
                  {activeFile && (
                    <span className="text-[10px] text-neutral-400 font-mono hidden sm:inline">
                      (UUID: {activeFile.id.substring(0,8)}...)
                    </span>
                  )}
                  <div className="flex-grow" />
                  <LocalSyncButton onSynced={fetchBlueprints} />
                </div>
              )}

              {/* Chat form */}
              <form onSubmit={handleSendMessage} className={`flex items-center space-x-3 p-2 bg-transparent w-full h-14 flex-shrink-0 ${
                activeMode === 'project' 
                  ? '' 
                  : 'border border-neutral-200/60 rounded-xl focus-within:ring-1 focus-within:ring-neutral-900 focus-within:bg-white'
              }`}>
                <input
                  type="text"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder={activeMode === 'general' ? "Cosmos Mode: General Intelligence Workspace" : "Code Mode: Project Intelligence Workspace"}
                  className="flex-grow bg-transparent text-sm pl-2 focus:outline-none text-neutral-900 h-full"
                  disabled={isThinking}
                />
                <button
                  type="submit"
                  disabled={isThinking || !message.trim()}
                  className="bg-neutral-900 hover:bg-black disabled:bg-neutral-200 text-white font-bold px-5 h-10 rounded-lg text-xs tracking-widest uppercase transition-colors flex items-center justify-center flex-shrink-0"
                >
                  {activeMode === 'general' ? 'Query' : 'Execute'}
                </button>
              </form>
            </div>
          </div>
        </section>

        {/* Right panel: Live agent activity feed */}
        <section className="lg:col-span-4 bg-white border border-neutral-100 rounded-2xl p-7 flex flex-col h-full shadow-[0_8px_30px_rgb(0,0,0,0.04)] backdrop-blur-sm overflow-hidden">
          <div className="flex items-center justify-between border-b border-neutral-100 pb-4 mb-4 flex-shrink-0">
            <div className="flex items-center space-x-2">
              <span className="text-xs text-neutral-400 font-mono">02 /</span>
              <h2 className="text-xs font-bold uppercase tracking-widest text-neutral-800">Live Agent Activity Feed</h2>
            </div>
            <button 
              onClick={fetchLiveFeeds} 
              className="text-xs font-mono tracking-wider uppercase text-neutral-400 hover:text-neutral-900 transition-colors"
            >
              [ Sync Feed ]
            </button>
          </div>

          <div className="flex-grow overflow-y-auto space-y-3.5 pr-1 scrollbar-thin min-h-0">
            {isLoadingFeed && liveFeeds.length === 0 ? (
              <div className="flex items-center justify-center h-48 animate-pulse text-xs text-neutral-400 font-mono">
                Loading live feeds...
              </div>
            ) : liveFeeds.length === 0 ? (
              <div className="flex items-center justify-center h-48 text-xs text-neutral-300 font-mono italic">
                No active logs captured in this session.
              </div>
            ) : (
              liveFeeds.map((node) => (
                <div
                  key={node.id}
                  onClick={() => handleNodeClick(node.id)}
                  className="group border border-neutral-100 rounded-xl p-4 bg-neutral-50/40 hover:bg-white hover:border-neutral-900 cursor-pointer transition-all duration-200 shadow-sm flex flex-col justify-between"
                >
                  <div>
                    <div className="flex justify-between items-center mb-1.5">
                      <h3 className="text-sm font-bold text-neutral-900 truncate max-w-[75%] group-hover:text-black">
                        <span className="text-neutral-350 group-hover:text-black transition-colors font-bold">▶ </span>
                        <span className="truncate">{node.title}</span>
                      </h3>
                      <span className="text-[9px] font-mono font-bold uppercase text-neutral-400 bg-neutral-100 px-1.5 py-0.5 rounded">
                        Active Node
                      </span>
                    </div>
                    <p className="text-sm text-neutral-500 line-clamp-2 leading-relaxed">
                      {node.content}
                    </p>
                  </div>
                  <div className="mt-2.5 pt-2 border-t border-neutral-100/60 flex justify-between items-center text-[9px] font-mono text-neutral-400">
                    <span>ID: {node.id.substring(0, 8)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

      </main>

      {isModalOpen && (
        <NodeDetailModal 
          nodeId={selectedNodeId} 
          onClose={() => {
            setIsModalOpen(false);
            setSelectedNodeId(null);
          }} 
        />
      )}
    </div>
  );
}