import {
  formatNumber,
} from "../lib/format";


interface StrengthBarProps {
  value: number;
  compact?: boolean;
}


export function StrengthBar({
  value,
  compact = false,
}: StrengthBarProps) {
  const normalizedValue = Math.min(
    100,
    Math.max(0, value),
  );

  return (
    <div
      className={
        `strength${
          compact
            ? " strength--compact"
            : ""
        }`
      }
    >
      <div className="strength__header">
        <span>Сила</span>

        <strong>
          {formatNumber(value)} / 100
        </strong>
      </div>

      <div
        className="strength__track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={normalizedValue}
      >
        <span
          className="strength__fill"
          style={{
            width: `${normalizedValue}%`,
          }}
        />
      </div>
    </div>
  );
}