// src/app/layout.tsx
import './globals.css';
import Header from '@/components/layout/Header';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-[#fafafa] antialiased flex flex-col selection:bg-neutral-900 selection:text-white">
        <Header />

        <main className="flex-grow w-full">
          {children}
        </main>
      </body>
    </html>
  );
}