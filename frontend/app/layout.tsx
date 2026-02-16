import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Workflow AI Assistant',
  description: 'AI-powered workflow design and visualization tool',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
