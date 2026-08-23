import { cn } from "@/lib/utils";

export function SectionFrame({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("corner-markers border border-black/15 bg-[#f5f4ef] p-4 md:p-6", className)}>
      <span className="corner-bl" aria-hidden />
      <span className="corner-br" aria-hidden />
      {children}
    </div>
  );
}
