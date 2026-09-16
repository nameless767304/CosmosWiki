'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Header() {
  const pathname = usePathname();

  return (
    <header className="fixed top-0 left-0 w-full bg-neutral-100/70 border-b border-neutral-200/50 py-5 px-8 z-50 backdrop-blur-md">
      <div className="max-w-7xl w-full mx-auto flex justify-between items-center">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-neutral-900 uppercase">
            <Link href="/">COSMOSWIKI</Link>
          </h1>
        </div>
        
        <div className="flex items-center space-x-6">
          <Link 
            href="/" 
            className={`text-xs uppercase tracking-widest transition-colors ${
              pathname === '/' ? 'text-neutral-900 font-extrabold' : 'text-neutral-400 font-medium hover:text-neutral-600'
            }`}
          >
            Dashboard
          </Link>
          <Link 
            href="/archive" 
            className={`text-xs uppercase tracking-widest transition-colors ${
              pathname === '/archive' ? 'text-neutral-900 font-extrabold' : 'text-neutral-400 font-medium hover:text-neutral-600'
            }`}
          >
            Archive List
          </Link>
        </div>
      </div>
    </header>
  );
}