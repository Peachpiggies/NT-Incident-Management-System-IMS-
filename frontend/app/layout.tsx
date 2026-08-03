import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Incident Management Platform',
  description: 'Incident Management Platform (IMP)',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
