import { useState } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { searchAPI } from '../lib/api';
import { cleanText } from '../lib/cleanText';

export default function SearchView() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  const doSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await searchAPI(query);
      setResults(data);
    } catch (e) {
      setResults([{ title: 'Error', text: e.message, score: 0, profile: 'error' }]);
    }
    setLoading(false);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-4 border-b border-border">
        <div className="flex gap-2">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doSearch()}
            placeholder="Search protocols..."
            className="flex-1 px-4 py-2.5 rounded-xl bg-surface-2 border border-border text-sm text-text
              focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-text-2/60"
          />
          <button
            onClick={doSearch}
            disabled={loading}
            className="p-2.5 rounded-xl bg-accent text-white hover:bg-accent/90 transition disabled:opacity-50"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Search size={18} />}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {results.map((r, i) => (
          <div key={i} className="p-4 rounded-xl bg-surface-2 border border-border space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase
                  ${r.profile === 'core' ? 'bg-accent/20 text-accent' : 'bg-green/20 text-green'}`}>
                  {r.profile}
                </span>
                <span className="text-sm font-medium">{r.title}</span>
              </div>
              <span className="text-xs text-text-2">{(r.score * 100).toFixed(0)}%</span>
            </div>
            <p className="text-xs text-text-2 leading-relaxed">{cleanText(r.text)}</p>
          </div>
        ))}

        {results.length === 0 && !loading && (
          <div className="text-center py-20">
            <Search size={32} className="mx-auto text-text-2/30 mb-3" />
            <p className="text-sm text-text-2">Search the knowledge base directly</p>
          </div>
        )}
      </div>
    </div>
  );
}
