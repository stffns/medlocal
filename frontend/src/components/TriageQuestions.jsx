import { useState } from 'react';
import { Check, X, Loader2 } from 'lucide-react';

export default function TriageQuestions({ questions, onSubmit }) {
  const [answers, setAnswers] = useState({});
  const [sending, setSending] = useState(false);

  const toggle = (idx, value) => {
    setAnswers(prev => ({ ...prev, [idx]: prev[idx] === value ? null : value }));
  };

  const [done, setDone] = useState(false);

  const handleSubmit = async () => {
    const parts = [];
    questions.forEach((q, i) => {
      if (answers[i]) parts.push(`${q.text}: ${answers[i]}`);
    });
    if (!parts.length) return;
    setSending(true);
    await onSubmit(parts);
    setDone(true);
  };

  if (done) {
    // Show answered summary
    return (
      <div className="mt-4 pt-4 border-t border-border space-y-2 opacity-70">
        {questions.map((q, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span className={`px-1.5 py-0.5 rounded font-semibold ${answers[i] === 'yes' ? 'bg-green/20 text-green' : answers[i] === 'no' ? 'bg-red/20 text-red' : 'bg-surface-3 text-text-2'}`}>
              {answers[i] || '—'}
            </span>
            <span className="text-text-2">{q.text}</span>
          </div>
        ))}
      </div>
    );
  }

  const answeredCount = Object.values(answers).filter(Boolean).length;

  return (
    <div className="mt-4 pt-4 border-t border-border space-y-3">
      {questions.map((q, i) => (
        <div key={i} className="space-y-1.5">
          <p className="text-sm font-medium text-text">{q.text}</p>
          <div className="flex items-center gap-2">
            {q.type === 'yes_no' ? (
              <>
                <button
                  onClick={() => toggle(i, 'yes')}
                  disabled={sending}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold transition-all
                    ${answers[i] === 'yes'
                      ? 'bg-green text-black shadow-md shadow-green/20'
                      : 'bg-surface-3 text-text-2 hover:bg-surface-3/80'
                    } disabled:opacity-50`}
                >
                  <Check size={14} /> Yes
                </button>
                <button
                  onClick={() => toggle(i, 'no')}
                  disabled={sending}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold transition-all
                    ${answers[i] === 'no'
                      ? 'bg-red text-white shadow-md shadow-red/20'
                      : 'bg-surface-3 text-text-2 hover:bg-surface-3/80'
                    } disabled:opacity-50`}
                >
                  <X size={14} /> No
                </button>
              </>
            ) : (
              <input
                type="text"
                placeholder="Type answer..."
                disabled={sending}
                onChange={e => setAnswers(prev => ({ ...prev, [i]: e.target.value || null }))}
                className="px-3 py-2 bg-surface-3 border border-border rounded-lg text-sm text-text w-3/5 focus:outline-none focus:ring-1 focus:ring-accent"
              />
            )}
            {q.source && (
              <span className="text-[10px] text-text-2 ml-1">{q.source}</span>
            )}
          </div>
          {answers[i] && q[`if_${answers[i]}`] && (
            <p className={`text-xs pl-1 ${answers[i] === 'yes' && q.if_yes?.toLowerCase().includes('peligro') || answers[i] === 'yes' && q.if_yes?.toLowerCase().includes('danger') ? 'text-red' : 'text-text-2'}`}>
              {q[`if_${answers[i]}`]}
            </p>
          )}
        </div>
      ))}

      <button
        onClick={handleSubmit}
        disabled={sending || answeredCount === 0}
        className="w-full mt-2 py-3 rounded-xl text-sm font-bold transition-all
          bg-green text-black hover:bg-green/90 disabled:bg-surface-3 disabled:text-text-2 disabled:cursor-not-allowed
          flex items-center justify-center gap-2"
      >
        {sending ? (
          <><Loader2 size={16} className="animate-spin" /> Analyzing...</>
        ) : (
          `Send answers (${answeredCount}/${questions.length})`
        )}
      </button>
    </div>
  );
}
