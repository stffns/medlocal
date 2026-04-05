const STYLES = {
  HIGH: 'bg-green text-black',
  MEDIUM: 'bg-yellow text-black',
  LOW: 'bg-red text-white',
  EMERGENCY: 'bg-red text-white animate-pulse',
  EMERGENCY_DETECTED: 'bg-red/80 text-white',
  URGENT_REFERRAL: 'bg-orange-500 text-white',
  DEFAULT: 'bg-surface-3 text-text-2',
};

export default function Badge({ label, variant }) {
  const cls = STYLES[variant || label] || STYLES.DEFAULT;
  return (
    <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wide ${cls}`}>
      {label}
    </span>
  );
}
