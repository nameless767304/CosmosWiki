'use client';

import React, { useState, useEffect } from 'react';
import { BACKEND_URL } from '@/config'; 

interface NodeDetailModalProps {
  nodeId: string | null;
  onClose: () => void;
  onDeleteSuccess?: () => void;
}

interface AssociatedLink {
  id: string;
  title: string;
  similarity: number;
}

interface NodeData {
  id: string;
  title: string;
  content: string;
  created_at?: string;
}

export default function NodeDetailModal({ nodeId, onClose, onDeleteSuccess }: NodeDetailModalProps) {
  const [nodeData, setNodeData] = useState<NodeData | null>(null);

  const [associatedLinks, setAssociatedLinks] = useState<AssociatedLink[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editContent, setEditContent] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!nodeId) return;

    const fetchModalData = async () => {
      setIsLoading(true);
      try {
        const nodeRes = await fetch(`${BACKEND_URL}/wiki/nodes`);
        if (nodeRes.ok) {
          const allNodes = await nodeRes.json();
          const targetNode = (allNodes.nodes || allNodes || []).find((n: NodeData) => n.id === nodeId);
          if (targetNode) {
            setNodeData(targetNode);
            setEditTitle(targetNode.title);
            setEditContent(targetNode.content);
          }
        }

        const linkRes = await fetch(`${BACKEND_URL}/wiki/links/${nodeId}`);
        if (linkRes.ok) {
          const linkData = await linkRes.json();
          setAssociatedLinks(linkData.links || []);
        }
      } catch (err) {
        console.error('Failed to load modal data:', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchModalData();
    setIsEditing(false);
  }, [nodeId]);

  const handleDelete = async () => {
    if (!window.confirm("이 노드를 삭제하시겠습니까?")) return;

    setIsDeleting(true);
    try {
      const res = await fetch(`${BACKEND_URL}/wiki/delete/${nodeId}`, {
        method: 'DELETE',
      });

      if (res.ok) {
        onClose(); 
        if (onDeleteSuccess) onDeleteSuccess(); 
      } else {
        alert("노드를 삭제하지 못했습니다.");
      }
    } catch (err) {
      console.error('Failed to delete node:', err);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleSave = async () => {
    if (!editTitle.trim() || !editContent.trim()) {
      alert("제목과 내용을 모두 입력해 주세요.");
      return;
    }

    setIsSaving(true);
    try {
      const res = await fetch(`${BACKEND_URL}/wiki/update/${nodeId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: editTitle,
          content: editContent
        }),
      });

      if (res.ok) {
        setNodeData(prev => prev ? { ...prev, title: editTitle, content: editContent } : null);
        setIsEditing(false);
        if (onDeleteSuccess) onDeleteSuccess(); 
      } else {
        alert("수정에 실패했습니다.");
      }
    } catch (err) {
      console.error('Failed to update node:', err);
    } finally {
      setIsSaving(false);
    }
  };

  if (!nodeId) return null;

  return (
    <div className="fixed inset-0 bg-neutral-900/40 backdrop-blur-sm flex items-center justify-center z-[100] p-4 animate-fadeIn">
      
      <div className="bg-white border border-neutral-200/80 rounded-2xl w-full max-w-2xl shadow-[0_20px_50px_rgba(0,0,0,0.12)] max-h-[85vh] flex flex-col overflow-hidden animate-slideUp">
        
        <div className="p-6 border-b border-neutral-100 flex justify-between items-start bg-neutral-50/50 flex-shrink-0">
          <div>
            <span className="text-xs font-mono font-bold uppercase tracking-widest text-neutral-400">
              Node Info.
            </span>
            <h2 className="text-base font-bold text-neutral-900 mt-1 truncate max-w-[450px] flex items-center gap-1.5">
              {isLoading ? 'Loading...' : (
                <>
                  <span className="text-neutral-350 font-bold">&gt;</span>
                  {isEditing ? (
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      className="w-full bg-neutral-50 border border-neutral-200 rounded-lg px-2.5 py-1 text-sm font-bold text-neutral-900 focus:outline-none focus:border-neutral-900 transition-colors"
                      placeholder="제목을 입력해 주세요."
                    />
                  ) : (
                    <span>{nodeData?.title || 'Loading Title...'}</span>
                  )}
                </>
              )}
            </h2>
          </div>
          <button 
            onClick={onClose}
            className="text-neutral-400 hover:text-black font-mono text-sm border border-neutral-200 bg-white hover:bg-neutral-50 px-2.5 py-1 rounded-lg transition-colors shadow-sm"
          >
            ESC
          </button>
        </div>

        {/* Content and links */}
        <div className="p-6 overflow-y-auto space-y-6 min-h-0 scrollbar-thin">
          {isLoading ? (
            <div className="flex items-center justify-center h-48 animate-pulse text-xs text-neutral-400 font-mono">
              Loading data...
            </div>
          ) : (
            <>
              {/* Document context */}
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-widest text-neutral-400">
                  Document Context Contents
                </h4>
                {isEditing ? (
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    rows={6}
                    className="w-full bg-neutral-50/70 border border-neutral-200 rounded-xl p-4 text-sm text-neutral-800 leading-relaxed font-normal focus:outline-none focus:border-neutral-900 transition-colors resize-none scrollbar-thin font-mono"
                    placeholder="내용을 입력해 주세요."
                  />
                ) : (
                  <div className="bg-neutral-50/70 border border-neutral-200/40 rounded-xl p-4 text-sm text-neutral-800 leading-relaxed font-normal whitespace-pre-wrap">
                    {nodeData?.content || '내용이 없습니다.'}
                  </div>
                )}
              </div>

              {/* Associated links */}
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-widest text-neutral-400">
                  Associated Knowledge Networks (Similarity Web)
                </h4>
                
                {associatedLinks.length === 0 ? (
                  <p className="text-xs text-neutral-400 font-mono italic pl-1">
                    Isolated node. No active similarity thresholds triggered in the knowledge graph.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 gap-2.5">
                    {associatedLinks.map((link) => (
                      <div 
                        key={link.id}
                        className="flex justify-between items-center bg-white border border-neutral-200/70 rounded-xl p-3.5 hover:border-neutral-900 transition-all shadow-sm group"
                      >
                        <div className="flex items-center space-x-2 truncate max-w-[80%]">
                          <span className="text-sm font-bold text-neutral-700 truncate group-hover:text-black flex items-center gap-1.5">
                            <span className="text-neutral-350 font-bold">&gt;</span>
                            {link.title}
                          </span>
                        </div>
                        <div className="flex items-center space-x-2 flex-shrink-0">
                          <span className="text-xs font-mono text-neutral-400">Weight:</span>
                          <span className="text-xs font-mono font-extrabold bg-neutral-900 text-white px-2 py-0.5 rounded-md">
                            {link.similarity}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 bg-neutral-50/50 border-t border-neutral-100 flex justify-between items-center flex-shrink-0 px-6">
          
          {/* Action buttons */}
          <div className="flex items-center space-x-2">
            <button
              onClick={handleDelete}
              disabled={isDeleting || isLoading || isSaving}
              className="text-xs font-bold uppercase tracking-widest text-red-500 hover:text-white bg-transparent hover:bg-red-600 border border-red-200/50 hover:border-red-600 px-3 py-1.5 rounded-xl disabled:text-neutral-200 disabled:bg-transparent disabled:border-transparent transition-all duration-200 font-mono cursor-pointer shadow-sm"
            >
              {isDeleting ? "Destroying..." : "Delete Node"}
            </button>
            
            {!isEditing && (
              <button
                onClick={() => setIsEditing(true)}
                disabled={isLoading || isDeleting}
                className="text-xs font-bold uppercase tracking-widest text-neutral-500 hover:text-white bg-transparent hover:bg-neutral-600 border border-neutral-200/50 hover:border-neutral-600 px-3 py-1.5 rounded-xl disabled:text-neutral-200 disabled:bg-transparent disabled:border-transparent transition-all duration-200 font-mono cursor-pointer shadow-sm"
              >
                Edit Node
              </button>
            )}
          </div>
          
          {/* Controls */}
          <div className="flex items-center space-x-3">
            {isEditing ? (
              <>
                <button
                  onClick={() => {
                    setEditTitle(nodeData?.title || '');
                    setEditContent(nodeData?.content || '');
                    setIsEditing(false);
                  }}
                  disabled={isSaving}
                  className="text-xs font-bold uppercase tracking-wider text-neutral-500 hover:text-black font-mono border border-neutral-200 bg-white hover:bg-neutral-50 px-3 py-1.5 rounded-xl transition-all shadow-sm cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={isSaving}
                  className="text-xs font-bold uppercase tracking-wider text-white bg-neutral-900 hover:bg-black font-mono px-4 py-1.5 rounded-xl transition-all shadow-md cursor-pointer flex items-center gap-1"
                >
                  {isSaving ? "Saving..." : "Save Changes"}
                </button>
              </>
            ) : (
              <>
                <div className="text-xs font-mono text-neutral-400 tracking-wider uppercase hidden sm:block">
                  UID: {nodeData?.id ? nodeData.id.substring(0, 8) : '--------'}
                </div>
              </>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}