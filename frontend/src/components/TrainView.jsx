import { useState, useEffect } from 'react';
import { GraduationCap, ChevronRight, Loader2, Check, X, RotateCcw } from 'lucide-react';
import { trainSessionAPI, trainAnswerAPI, trainTopicsAPI, trainGenerateAPI } from '../lib/api';

function CardView({ card, onAnswer }) {
  const [flipped, setFlipped] = useState(false);
  const [userAnswer, setUserAnswer] = useState('');
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!userAnswer.trim()) return;
    setSubmitting(true);
    try {
      const r = await trainAnswerAPI(card.id, userAnswer);
      setResult(r);
    } catch (e) {
      setResult({ rating: 'error', feedback: e.message, correct_answer: card.answer, next_review_days: 0 });
    }
    setSubmitting(false);
  };

  const ratingColor = { excellent: 'text-green', good: 'text-accent', fair: 'text-yellow', poor: 'text-red' };

  return (
    <div className="p-5 rounded-2xl bg-surface-2 border border-border space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-text-2 bg-surface-3 px-2 py-0.5 rounded-full">{card.level_label}</span>
        <span className="text-xs text-text-2">{card.source_title}</span>
      </div>

      <p className="text-sm font-medium leading-relaxed">{card.question}</p>

      {card.is_read_only ? (
        <div className="space-y-2">
          <button onClick={() => setFlipped(!flipped)} className="text-xs text-accent hover:underline">
            {flipped ? 'Hide answer' : 'Show answer'}
          </button>
          {flipped && (
            <div className="p-3 rounded-lg bg-surface-3/50 text-sm text-text-2 leading-relaxed">
              {card.answer}
            </div>
          )}
        </div>
      ) : result ? (
        <div className="space-y-2">
          <div className={`text-sm font-semibold ${ratingColor[result.rating] || 'text-text-2'}`}>
            {result.rating.toUpperCase()} — next review in {result.next_review_days} days
          </div>
          <p className="text-sm text-text-2">{result.feedback}</p>
          <details className="text-xs">
            <summary className="text-text-2 cursor-pointer">Correct answer</summary>
            <p className="mt-1 p-2 rounded bg-surface-3/50 text-text-2">{result.correct_answer}</p>
          </details>
        </div>
      ) : (
        <div className="space-y-2">
          <textarea
            value={userAnswer}
            onChange={e => setUserAnswer(e.target.value)}
            placeholder="Type your answer..."
            rows={3}
            className="w-full px-3 py-2 rounded-lg bg-surface-3 border border-border text-sm text-text resize-none
              focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-text-2/60"
          />
          <button
            onClick={handleSubmit}
            disabled={submitting || !userAnswer.trim()}
            className="w-full py-2 rounded-lg bg-accent text-white text-sm font-semibold hover:bg-accent/90
              disabled:bg-surface-3 disabled:text-text-2 flex items-center justify-center gap-2"
          >
            {submitting ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
            Submit
          </button>
        </div>
      )}
    </div>
  );
}

export default function TrainView() {
  const [topics, setTopics] = useState([]);
  const [selectedTopic, setSelectedTopic] = useState(null);
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genTopic, setGenTopic] = useState('');

  useEffect(() => {
    trainTopicsAPI().then(setTopics).catch(() => {});
  }, []);

  const loadSession = async (topic) => {
    setSelectedTopic(topic);
    setLoading(true);
    try {
      const data = await trainSessionAPI(topic);
      setCards(data.cards);
    } catch {
      setCards([]);
    }
    setLoading(false);
  };

  const generateCards = async () => {
    if (!genTopic.trim()) return;
    setGenerating(true);
    try {
      await trainGenerateAPI(genTopic);
      const data = await trainTopicsAPI();
      setTopics(data);
      setGenTopic('');
    } catch {}
    setGenerating(false);
  };

  if (selectedTopic !== null) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <button onClick={() => { setSelectedTopic(null); setCards([]); }} className="text-text-2 hover:text-text">
            <RotateCcw size={16} />
          </button>
          <h2 className="text-sm font-semibold flex-1">{selectedTopic || 'All topics'}</h2>
          <span className="text-xs text-text-2">{cards.length} cards</span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 size={24} className="animate-spin text-accent" />
            </div>
          ) : cards.length === 0 ? (
            <p className="text-center text-sm text-text-2 py-20">No cards due for review</p>
          ) : (
            cards.map(c => <CardView key={c.id} card={c} />)
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-4 border-b border-border space-y-3">
        <div className="flex gap-2">
          <input
            value={genTopic}
            onChange={e => setGenTopic(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && generateCards()}
            placeholder="Generate cards for topic..."
            className="flex-1 px-4 py-2.5 rounded-xl bg-surface-2 border border-border text-sm text-text
              focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-text-2/60"
          />
          <button
            onClick={generateCards}
            disabled={generating}
            className="px-4 py-2.5 rounded-xl bg-accent text-white text-sm font-semibold hover:bg-accent/90 disabled:opacity-50"
          >
            {generating ? <Loader2 size={16} className="animate-spin" /> : 'Generate'}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
        <button
          onClick={() => loadSession(null)}
          className="w-full flex items-center justify-between p-4 rounded-xl bg-surface-2 border border-border hover:border-accent/50 transition"
        >
          <span className="text-sm font-medium">All topics</span>
          <ChevronRight size={16} className="text-text-2" />
        </button>

        {topics.map(t => (
          <button
            key={t}
            onClick={() => loadSession(t)}
            className="w-full flex items-center justify-between p-4 rounded-xl bg-surface-2 border border-border hover:border-accent/50 transition"
          >
            <span className="text-sm font-medium">{t}</span>
            <ChevronRight size={16} className="text-text-2" />
          </button>
        ))}

        {topics.length === 0 && (
          <div className="text-center py-20">
            <GraduationCap size={32} className="mx-auto text-text-2/30 mb-3" />
            <p className="text-sm text-text-2">No training topics yet</p>
            <p className="text-xs text-text-2/60 mt-1">Generate cards from a topic above</p>
          </div>
        )}
      </div>
    </div>
  );
}
