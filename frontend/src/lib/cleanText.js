/** Clean LaTeX artifacts and protocol references from model output. */
export function cleanText(text) {
  if (!text) return '';
  return text
    .replace(/\\ge(?:q)?\s*/g, '>=')
    .replace(/\\le(?:q)?\s*/g, '<=')
    .replace(/\\circ/g, '°')
    .replace(/\^\{([^}]*)\}/g, '$1')
    .replace(/\\times/g, '×')
    .replace(/\\pm/g, '±')
    .replace(/\\text\{([^}]*)\}/g, '$1')
    .replace(/\$([^$]+)\$/g, '$1')
    .replace(/\bprotocol[_\s]*\d+\b/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

/** Convert inline markdown **bold** to JSX-safe HTML string. */
export function inlineMd(text) {
  if (!text) return '';
  return cleanText(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

