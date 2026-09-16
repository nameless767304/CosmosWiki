'use client';

import React, { useState } from 'react';
import { BACKEND_URL } from '@/config';

interface LocalSyncButtonProps {
  onSynced: () => void;
}

export default function LocalSyncButton({ onSynced }: LocalSyncButtonProps) {
  const [isSyncing, setIsSyncing] = useState(false);

  const handleSync = async () => {
    setIsSyncing(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/project/sync-local`, {
        method: 'POST',
      });
      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || 'Sync error');

      alert(
        `로컬 코드 동기화 완료\n` +
        `파일: ${data.scanned_files}개 / 함수: ${data.functions_indexed}개 / ` +
        `의존성: ${data.relations_mapped}개 / 제거: ${data.removed_files}개`
      );
      onSynced();
    } catch (error) {
      console.error('Local sync failed:', error);
      alert('로컬 코드 동기화 중 오류가 발생했습니다.');
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <button
      onClick={handleSync}
      disabled={isSyncing}
      className="bg-neutral-900 hover:bg-black disabled:bg-neutral-200 text-white font-bold px-2.5 py-1 rounded-md text-[10px] tracking-wider uppercase transition-colors flex items-center justify-center flex-shrink-0"
    >
      {isSyncing ? 'Syncing...' : 'Sync Local Code'}
    </button>
  );
}
