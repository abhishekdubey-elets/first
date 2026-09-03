import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Providers } from '@/lib/providers';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'IAS Transfer Intelligence — Real-time officer transfer tracking',
  description:
    'Autonomous intelligence on IAS officer transfers: AI-powered discovery, extraction, web enrichment, analytics, and Google Sheets sync — updated hourly.',
  openGraph: {
    title: 'IAS Transfer Intelligence',
    description:
      'Autonomous, AI-powered tracking of IAS officer transfers across India.',
    type: 'website',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`dark ${inter.variable}`}>
      <body className="font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
