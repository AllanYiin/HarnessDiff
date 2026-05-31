import type { SurfaceType } from "../types";

type SurfaceSegmentedControlProps = {
  value: SurfaceType;
  disabled?: boolean;
  onChange: (value: SurfaceType) => void;
};

const options: { value: SurfaceType; label: string }[] = [
  { value: "chat", label: "Chat" },
  { value: "agent", label: "Agent" }
];

export function SurfaceSegmentedControl({
  value,
  disabled = false,
  onChange
}: SurfaceSegmentedControlProps) {
  return (
    <div className="surfaceSegmented" role="tablist" aria-label="Surface mode">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          className={value === option.value ? "selected" : ""}
          aria-selected={value === option.value}
          disabled={disabled}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
