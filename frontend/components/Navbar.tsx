import Link from "next/link";

export function Navbar() {
  return (
    <header className="sticky top-0 z-40 border-b border-black/10 bg-[#f5f4ef]/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 md:px-6">
        <Link href="/" className="group">
          <p className="text-[10px] uppercase tracking-[0.35em] text-black/45">Bhopal Monitor</p>
          <p className="text-lg font-semibold tracking-tight">THE MP GAZETTE</p>
        </Link>
        <nav className="flex items-center gap-4 text-xs uppercase tracking-[0.2em] text-black/60">
          <Link href="/" className="hover:text-black">Edition</Link>
          <Link href="/chains" className="hover:text-black">Chains</Link>
          <Link href="/events" className="hover:text-black">Tracked</Link>
          <Link href="/search" className="hover:text-black">Search</Link>
        </nav>
      </div>
    </header>
  );
}
