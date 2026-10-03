interface Props {
  label: string;
  icon: string;
  value: number | null;
  low: number; // below this the bar turns to the warning color
  color: string;
}

/** A big, kid-readable level bar for moisture or light. */
export function Gauge({ label, icon, value, low, color }: Props) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  const isLow = value != null && value < low;
  return (
    <div className={`gauge ${isLow ? "gauge-low" : ""}`}>
      <div className="gauge-head">
        <span className="gauge-icon" aria-hidden>{icon}</span>
        <span className="gauge-label">{label}</span>
        <span className="gauge-value">{value == null ? "–" : `${Math.round(pct)}%`}</span>
      </div>
      <div className="gauge-track" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
        <div className="gauge-fill" style={{ width: `${pct}%`, background: isLow ? "var(--warn)" : color }} />
        <div className="gauge-mark" style={{ left: `${low}%` }} />
      </div>
    </div>
  );
}
