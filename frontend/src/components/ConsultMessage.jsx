import { useState } from 'react';
import { ChevronDown, ChevronUp, FileText, AlertTriangle, Activity, ClipboardList, BookOpen, Eye, RotateCcw } from 'lucide-react';
import Badge from './Badge';
import TriageQuestions from './TriageQuestions';
import { cleanText, inlineMd } from '../lib/cleanText';
import { getChunkAPI } from '../lib/api';

function SourceViewer({ sources }) {
  const [open, setOpen] = useState(false);
  const [viewingChunk, setViewingChunk] = useState(null);

  if (!sources?.length) return null;

  const viewChunk = async (chunkId, profile) => {
    try {
      const data = await getChunkAPI(chunkId, profile);
      setViewingChunk(data.text);
    } catch {
      setViewingChunk('Error loading source');
    }
  };

  return (
    <div className="mt-3 pt-3 border-t border-border/50">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-text-2 hover:text-text transition"
      >
        <FileText size={12} />
        Retrieved protocols ({sources.length})
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      {open && (
        <div className="mt-2 space-y-1">
          {sources.slice(0, 3).map((s, i) => (
            <button
              key={i}
              onClick={() => viewChunk(s.chunk_id, s.profile)}
              className="block text-left w-full px-2 py-1 rounded text-xs hover:bg-surface-3/50 transition"
            >
              <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase mr-1.5 ${s.profile === 'core' ? 'bg-accent/20 text-accent' : 'bg-green/20 text-green'}`}>
                {s.profile}
              </span>
              <span className="text-text-2">{s.title}</span>
            </button>
          ))}
          {viewingChunk && (
            <div className="mt-2 p-3 bg-surface rounded-lg border border-border max-h-60 overflow-auto">
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs font-semibold text-text-2">Protocol source</span>
                <button onClick={() => setViewingChunk(null)} className="text-xs text-text-2 hover:text-text">Close</button>
              </div>
              <pre className="text-xs text-text-2 whitespace-pre-wrap">{viewingChunk}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Render structured clinical response with clear visual sections. */
function StructuredResponse({ r }) {
  const isAssessment = r.mode === 'assessment';
  const rawCondition = cleanText(r.condition || '');
  // Filter out non-clinical condition values the model sometimes returns
  const condition = /^(missing_info|unknown|n\/a|none|undefined|assessment|guidance|desconocido|no se puede determinar)$/i.test(rawCondition) ? '' : rawCondition;
  const rawAssessment = cleanText(r.assessment || '');
  const assessment = /^(assessment|guidance)$/i.test(rawAssessment) ? '' : rawAssessment;
  const actions = (r.actions || [])
    .map(a => cleanText(a.replace(/^\s*\d+[.)]\s*/, '')))
    .filter(a => !/^(ask one question|explain briefly why)/i.test(a)); // filter echoed system instructions
  const referIf = (r.refer_if || []).map(cleanText).filter(s => s && !/^n\/?a$/i.test(s));
  const rawSource = cleanText(r.source_protocol || '');
  const sourceProtocol = /^n\/?a$/i.test(rawSource) ? '' : rawSource;
  // Clean "Suggested search terms:" from visual description
  const visualDesc = (r.visual_description || '')
    .replace(/\s*Suggested search terms?:.*$/im, '')       // remove search terms line
    .replace(/\*?(?:\(Note|Note):.*?(?:\)\*?|\*|$)/gis, '') // remove meta-notes in any format
    .trim();

  return (
    <div className="space-y-3">
      {/* Visual findings from image */}
      {visualDesc && (
        <div className="flex items-start gap-2 p-3 rounded-lg bg-accent/5 border border-accent/20">
          <Eye size={14} className="mt-0.5 shrink-0 text-accent" />
          <div>
            <span className="text-xs uppercase tracking-wide text-accent font-semibold">Visual findings</span>
            <p className="text-sm text-text/80 leading-relaxed mt-0.5">{visualDesc}</p>
          </div>
        </div>
      )}

      {/* Condition header */}
      {condition && (
        <div className="flex items-start gap-2">
          <Activity size={16} className={`mt-0.5 shrink-0 ${isAssessment ? 'text-yellow' : 'text-green'}`} />
          <div>
            <span className="text-xs uppercase tracking-wide text-text-2">
              {isAssessment ? 'Evaluating' : 'Assessment'}
            </span>
            <h3 className="text-base font-bold text-text -mt-0.5">{condition}</h3>
          </div>
        </div>
      )}

      {/* Assessment text */}
      {assessment && (
        <p className="text-sm text-text/90 leading-relaxed pl-6" dangerouslySetInnerHTML={{ __html: inlineMd(assessment) }} />
      )}

      {/* Actions */}
      {actions.length > 0 && (
        <div className="pl-6 space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-accent font-semibold">
            <ClipboardList size={13} />
            {isAssessment ? 'While assessing' : 'Actions'}
          </div>
          <ol className="space-y-2">
            {actions.map((a, i) => (
              <li key={i} className="flex gap-2 text-sm leading-relaxed">
                <span className="shrink-0 w-5 h-5 rounded-full bg-accent/15 text-accent text-xs font-bold flex items-center justify-center mt-0.5">
                  {i + 1}
                </span>
                <span className="text-text/90" dangerouslySetInnerHTML={{ __html: inlineMd(a) }} />
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Refer if */}
      {referIf.length > 0 && (
        <div className="pl-6 p-3 rounded-lg bg-red/5 border border-red/20 break-words">
          <div className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-red font-semibold mb-1.5">
            <AlertTriangle size={13} />
            Refer immediately if
          </div>
          <ul className="space-y-1">
            {referIf.map((r, i) => (
              <li key={i} className="text-sm text-red/80 flex items-start gap-1.5">
                <span className="text-red mt-1.5 text-[6px]">●</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Source protocol */}
      {sourceProtocol && (
        <div className="pl-6 flex items-center gap-1.5 text-xs text-text-2">
          <BookOpen size={12} />
          {sourceProtocol}
        </div>
      )}
    </div>
  );
}

export default function ConsultMessage({ message, onTriageSubmit, onRetry }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] px-4 py-3 rounded-2xl rounded-br-md bg-accent text-white text-sm space-y-2">
          {message.image && (
            <img src={message.image} alt="" className="w-32 h-32 rounded-lg object-cover" />
          )}
          <p>{message.content}</p>
        </div>
      </div>
    );
  }

  const r = message.data;
  if (!r) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[85%] px-4 py-3 rounded-2xl rounded-bl-md bg-surface-2 border border-border text-sm text-text/90 space-y-2">
          <p>{message.content}</p>
          {message.error && message.retryQuestion && onRetry && (
            <button
              onClick={() => onRetry(message)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent/10 text-accent text-xs font-medium hover:bg-accent/20 transition"
            >
              <RotateCcw size={12} />
              Retry
            </button>
          )}
        </div>
      </div>
    );
  }

  const isAssessment = r.mode === 'assessment';
  const hasStructured = r.condition || (r.actions && r.actions.length > 0);

  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] px-5 py-4 rounded-2xl rounded-bl-md bg-surface-2 border border-border space-y-3 overflow-hidden">
        {/* Badges */}
        <div className="flex flex-wrap gap-1.5">
          {r.urgency === 'emergency' && <Badge label="EMERGENCY" variant="EMERGENCY" />}
          {r.urgency === 'urgent' && <Badge label="URGENT" variant="URGENT_REFERRAL" />}
          <Badge label={r.confidence} />
          {r.safety_flags?.filter(f => f !== 'EMERGENCY_DETECTED' && f !== 'URGENT_REFERRAL').map((f, i) => (
            <Badge key={i} label={f.replace(/_/g, ' ')} />
          ))}
        </div>

        {/* Structured content or fallback to markdown */}
        {hasStructured ? (
          <StructuredResponse r={r} />
        ) : (
          <div className="prose text-sm leading-relaxed">
            {cleanText(r.answer).split('\n').map((line, i) => (
              <p key={i}>{line}</p>
            ))}
          </div>
        )}

        {/* Triage questions */}
        {isAssessment && r.triage_questions?.length > 0 && (
          <TriageQuestions questions={r.triage_questions} onSubmit={onTriageSubmit} />
        )}

        {/* Sources */}
        <SourceViewer sources={r.sources} />
      </div>
    </div>
  );
}
