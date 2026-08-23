export function SectionHeader({
  number,
  tag,
  title,
  description,
}: {
  number?: string;
  tag?: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="mb-4 border-b border-black/10 pb-3">
      <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-[0.25em] text-black/45">
        {number ? <span>No. {number}</span> : null}
        {tag ? <span>· {tag}</span> : null}
      </div>
      <h2 className="text-xl font-semibold tracking-tight md:text-2xl">{title}</h2>
      {description ? <p className="mt-1 text-sm text-black/55">{description}</p> : null}
    </div>
  );
}
