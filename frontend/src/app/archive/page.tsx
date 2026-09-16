'use client';

import { useState, useEffect } from 'react';
import { BACKEND_URL } from '@/config'; 
import NodeDetailModal from '@/components/modals/NodeDetailModal';

export default function ArchivePage() {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState('');

  const [nodesList, setNodesList] = useState<{ id: string; title: string; content: string; created_at: string }[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Load archive nodes
  const fetchNodes = async () => {
    setIsLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/wiki/nodes`);
      if (res.ok) {
        const data = await res.json();
        setNodesList(data.nodes || data || []);
      }
    } catch (err) {
      console.error('Failed to load archive nodes:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchNodes();
  }, []);

  // Save node
  const handleSaveWiki = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title || !content) return;

    setIsSaving(true);
    setSaveStatus('저장 중입니다.');

    try {
      const res = await fetch(`${BACKEND_URL}/wiki/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content }),
      });

      if (res.ok) {
        setSaveStatus('지식 노드가 등록되었습니다.');
        setTitle('');
        setContent('');
        fetchNodes();
      } else {
        const data = await res.json();
        setSaveStatus(`저장 실패: ${data.detail || '요청을 처리할 수 없습니다.'}`);
      }
    } catch {
      setSaveStatus('요청 처리 중 오류가 발생했습니다.');
    } finally {
      setIsSaving(false);
    }
  };

  // Search filter
  const filteredNodes = nodesList.filter((node) => {
    const query = searchQuery.toLowerCase();
    return (
      node.title.toLowerCase().includes(query) ||
      node.content.toLowerCase().includes(query)
    );
  });

  const handleNodeClick = (nodeId: string) => {
    setSelectedNodeId(nodeId);
    setIsModalOpen(true);
  };

  return (
    <div className="h-screen w-full bg-[#fafafa] text-[#111111] font-sans p-8 pt-30 pb-6 flex flex-col justify-between selection:bg-neutral-900 selection:text-white overflow-hidden">
      
      <main className="max-w-7xl w-full mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 h-[calc(100vh-160px)] pb-2 items-stretch">
        
        {/* Archive panel */}
        <section className="lg:col-span-8 bg-white border border-neutral-100 rounded-2xl p-7 flex flex-col h-full shadow-[0_8px_30px_rgb(0,0,0,0.04)] backdrop-blur-sm overflow-hidden">
          
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-neutral-100 pb-4 mb-5 flex-shrink-0">
            <div className="flex items-center space-x-3">
              <span className="text-xs text-neutral-400 font-mono">01 /</span>
              <h2 className="text-xs font-bold uppercase tracking-widest text-neutral-800">
                Knowledge Archive
              </h2>
              <span className="text-xs font-mono text-neutral-400 bg-neutral-50 border border-neutral-200/60 px-2 py-0.5 rounded-md">
                Total: {filteredNodes.length}
              </span>
            </div>
            
            <div className="relative w-full md:w-64">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search nodes..."
                className="w-full bg-neutral-50/80 border border-neutral-200/80 rounded-xl px-3 py-1.5 text-xs focus:outline-none focus:border-neutral-900 focus:bg-white transition-all font-mono"
              />
            </div>
          </div>

          <div className="flex-grow overflow-y-auto pr-1 scrollbar-thin min-h-0">
            {isLoading && nodesList.length === 0 ? (
              <div className="flex items-center justify-center h-64 text-sm text-neutral-400 font-mono animate-pulse">
                Loading knowledge archive...
              </div>
            ) : filteredNodes.length === 0 ? (
              <div className="flex items-center justify-center h-64 border border-dashed border-neutral-200 rounded-xl bg-neutral-50/30">
                <p className="text-sm text-neutral-400 font-mono italic">
                  No matching entities found.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-5 pb-2">
                {filteredNodes.map((node) => (
                  <div 
                    key={node.id}
                    onClick={() => handleNodeClick(node.id)}
                    className="border border-neutral-200/60 rounded-xl p-5 hover:border-neutral-900 bg-neutral-50/30 hover:bg-white transition-all duration-200 flex flex-col justify-between shadow-sm cursor-pointer group"
                  >
                    <div>
                      <div className="flex justify-between items-start mb-3">
                        <h3 className="text-sm font-bold text-neutral-900 truncate max-w-[80%] group-hover:text-black flex items-center gap-1.5">
                          <span className="text-neutral-350 group-hover:text-black transition-colors font-bold flex-shrink-0">▶ </span>
                          <span className="truncate">{node.title}</span>
                        </h3>
                        <span className="text-[9px] font-mono text-neutral-400 bg-neutral-100 px-1.5 py-0.5 rounded-md">
                          Node
                        </span>
                      </div>
                      <p className="text-sm text-neutral-500 line-clamp-4 leading-relaxed mb-4">
                        {node.content}
                      </p>
                    </div>
                    
                    <div className="border-t border-neutral-100/80 pt-3 flex justify-between items-center text-[9px] font-mono text-neutral-400">
                      <span>ID: {node.id.substring(0, 8)}</span>
                      <span>{node.created_at ? new Date(node.created_at).toLocaleDateString() : ''}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* Entry form panel */}
        <section className="lg:col-span-4 bg-white border border-neutral-100 rounded-2xl p-7 flex flex-col justify-between h-full shadow-[0_8px_30px_rgb(0,0,0,0.04)] backdrop-blur-sm overflow-hidden">
          <div className="flex flex-col h-full justify-between">
            <div className="flex flex-col h-full">
              <div className="flex items-center space-x-2 border-b border-neutral-100 pb-4 mb-4">
                <span className="text-xs text-neutral-400 font-mono">02 /</span>
                <h2 className="text-xs font-bold uppercase tracking-widest text-neutral-800">Manual Entry</h2>
              </div>
              
              <form onSubmit={handleSaveWiki} className="flex-grow flex flex-col justify-between min-h-0">
                <div className="space-y-4 flex-grow flex flex-col min-h-0">
                  
                  <div className="space-y-1.5 flex-shrink-0">
                    <label className="block text-xs font-bold uppercase tracking-widest text-neutral-400">주제</label>
                    <input
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="주제를 입력해 주세요"
                      className="w-full bg-neutral-50/50 border border-neutral-200/60 rounded-xl px-4 py-2.5 text-sm font-normal text-neutral-900 focus:outline-none focus:border-neutral-900 focus:bg-white transition-all duration-200"
                      required
                    />
                  </div>
                  
                  <div className="space-y-1.5 flex-grow flex flex-col min-h-0">
                    <label className="block text-xs font-bold uppercase tracking-widest text-neutral-400 flex-shrink-0">본문</label>
                    <textarea
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      placeholder="내용을 입력해 주세요"
                      className="w-full flex-grow bg-neutral-50/50 border border-neutral-200/60 rounded-xl p-4 text-sm font-normal text-neutral-900 focus:outline-none focus:border-neutral-900 focus:bg-white transition-all duration-200 resize-none leading-relaxed min-h-0"
                      required
                    />
                  </div>
                  
                  <button
                    type="submit"
                    disabled={isSaving}
                    className="w-full bg-neutral-900 hover:bg-black disabled:bg-neutral-200 text-white font-bold text-xs tracking-widest uppercase py-3.5 rounded-xl shadow-lg transition-all duration-150 active:scale-[0.99] flex-shrink-0"
                  >
                    {isSaving ? 'Saving...' : 'Save Node'}
                  </button>
                </div>
              </form>
            </div>
          </div>

          {saveStatus && (
            <div className="mt-3 p-3 bg-neutral-50 rounded-xl border border-neutral-100 font-mono text-xs text-neutral-600 text-center tracking-tight flex-shrink-0">
              {saveStatus}
            </div>
          )}
        </section>

      </main>

      {isModalOpen && (
        <NodeDetailModal 
          nodeId={selectedNodeId} 
          onClose={() => {
            setIsModalOpen(false);
            setSelectedNodeId(null);
          }} 
          onDeleteSuccess={fetchNodes}
        />
      )}
    </div>
  );
}