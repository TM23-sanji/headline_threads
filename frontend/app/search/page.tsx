import { Suspense } from "react";

import { SearchContent } from "./SearchContent";

export default function SearchPage() {
  return (
    <Suspense fallback={<p className="px-4 py-8 text-sm text-black/50">Loading search...</p>}>
      <SearchContent />
    </Suspense>
  );
}
