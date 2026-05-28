import Link from "next/link";
import "./globals.css";

export const metadata = {
  title: "Dialectical Engine",
  description: "Local multi-model debate trees"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <Link className="brand" href="/">
            Dialectical Engine
          </Link>
          <nav aria-label="Primary">
            <Link href="/new">New</Link>
            <Link href="/settings">Settings</Link>
            <Link href="/admin/workers">Workers</Link>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}

