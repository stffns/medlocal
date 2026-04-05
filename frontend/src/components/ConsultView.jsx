import { useState, useRef, useEffect } from 'react';
import { Send, RotateCcw, Camera, Loader2 } from 'lucide-react';
import ConsultMessage from './ConsultMessage';
import { consultAPI, visionTriageAPI } from '../lib/api';

export default function ConsultView() {
  const [messages, setMessages] = useState([]);
  const [history, setHistory] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [pendingImage, setPendingImage] = useState(null);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  const sendQuestion = async (question, { silent = false, image = null } = {}) => {
    if (!question.trim() && !image) return;
    const img = image || pendingImage;
    setInput('');
    setPendingImage(null);
    setLoading(true);

    if (!silent) {
      setMessages(prev => [...prev, {
        role: 'user',
        content: question + (img ? ' [photo]' : ''),
        image: img ? URL.createObjectURL(img) : null,
      }]);
    }

    try {
      let r;
      if (img) {
        // Vision triage — send image + text context
        const vr = await visionTriageAPI(img, question);
        r = {
          answer: vr.answer,
          sources: vr.sources || [],
          confidence: vr.confidence || 'MEDIUM',
          safety_flags: vr.safety_flags || [],
          emergency: vr.emergency || false,
          urgency: vr.urgency || 'routine',
          mode: vr.mode || 'guidance',
          triage_questions: vr.triage_questions || [],
          condition: vr.condition || vr.description || '',
          assessment: vr.assessment || vr.answer || '',
          actions: vr.actions || [],
          refer_if: vr.refer_if || [],
          source_protocol: vr.source_protocol || '',
          visual_description: vr.description || '',
        };
      } else {
        r = await consultAPI(question, history);
      }
      setHistory(prev => [
        ...prev,
        { role: 'user', content: question },
        { role: 'assistant', content: r.answer },
      ]);
      setMessages(prev => [...prev, { role: 'assistant', content: r.answer, data: r }]);
    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${e.message}`,
        error: true,
      }]);
    }
    setLoading(false);
    inputRef.current?.focus();
  };

  const handleTriageSubmit = async (parts) => {
    const originalQ = history.find(m => m.role === 'user')?.content || '';
    const screening = parts.join('. ');
    // Carry visual context if present (from image triage)
    const lastAssistant = [...messages].reverse().find(m => m.data?.visual_description);
    const visualCtx = lastAssistant?.data?.visual_description
      ? ` (Visual: ${lastAssistant.data.visual_description.replace(/Suggested search terms?:.*$/i, '').slice(0, 150)})`
      : '';
    const fullQ = `${originalQ}${visualCtx}. [${screening}]`;
    await sendQuestion(fullQ, { silent: true });
  };

  const handleReset = () => {
    setMessages([]);
    setHistory([]);
    setInput('');
    setPendingImage(null);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendQuestion(input);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-4 py-20">
            <div className="w-16 h-16 rounded-2xl bg-accent/10 flex items-center justify-center">
              <span className="text-3xl">🩺</span>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-text">Clinical Consultation</h2>
              <p className="text-sm text-text-2 mt-1 max-w-sm">
                Describe symptoms or ask a clinical question. Backed by WHO/IMCI protocols.
              </p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center">
              {['Child with fever and cough', 'Pregnant woman headache', 'Wound not healing'].map(q => (
                <button
                  key={q}
                  onClick={() => { setInput(q); sendQuestion(q); }}
                  className="px-3 py-1.5 rounded-full bg-surface-2 border border-border text-xs text-text-2 hover:text-text hover:border-accent/50 transition"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <ConsultMessage
            key={i}
            message={msg}
            onTriageSubmit={handleTriageSubmit}
          />
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="px-5 py-4 rounded-2xl rounded-bl-md bg-surface-2 border border-border flex items-center gap-3">
              <Loader2 size={16} className="animate-spin text-accent" />
              <span className="text-sm text-text-2">Searching protocols...</span>
            </div>
          </div>
        )}
      </div>

      {/* Image preview */}
      {pendingImage && (
        <div className="px-4 pb-2">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-2 border border-border">
            <img src={URL.createObjectURL(pendingImage)} alt="" className="w-12 h-12 rounded object-cover" />
            <span className="text-xs text-text-2 flex-1">{pendingImage.name}</span>
            <button onClick={() => setPendingImage(null)} className="text-text-2 hover:text-red text-xs">Remove</button>
          </div>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-border px-4 py-3">
        <div className="flex items-end gap-2 max-w-3xl mx-auto">
          <input
            type="file"
            ref={fileRef}
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={e => e.target.files?.[0] && setPendingImage(e.target.files[0])}
          />
          <button
            onClick={() => fileRef.current?.click()}
            className="p-2.5 rounded-xl bg-surface-2 border border-border text-text-2 hover:text-text transition shrink-0"
            title="Camera"
          >
            <Camera size={18} />
          </button>

          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe symptoms or ask a follow-up..."
            rows={1}
            className="flex-1 px-4 py-2.5 rounded-xl bg-surface-2 border border-border text-sm text-text resize-none
              focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-text-2/60
              max-h-32 overflow-auto"
            style={{ minHeight: '42px' }}
          />

          <button
            onClick={() => sendQuestion(input)}
            disabled={loading || (!input.trim() && !pendingImage)}
            className="p-2.5 rounded-xl bg-accent text-white hover:bg-accent/90 transition shrink-0
              disabled:bg-surface-3 disabled:text-text-2 disabled:cursor-not-allowed"
          >
            <Send size={18} />
          </button>

          <button
            onClick={handleReset}
            className="p-2.5 rounded-xl bg-surface-2 border border-border text-text-2 hover:text-text transition shrink-0"
            title="New consultation"
          >
            <RotateCcw size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}
