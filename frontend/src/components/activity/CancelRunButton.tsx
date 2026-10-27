import React from "react";
import { Square } from "lucide-react";

interface CancelRunButtonProps {
  onCancel: (event: React.MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
}

/** Compact stop button shown on `running` activity rows. */
export const CancelRunButton: React.FC<CancelRunButtonProps> = ({
  onCancel,
  disabled,
}) => (
  <button
    type="button"
    onClick={onCancel}
    disabled={disabled}
    title="Cancel this run"
    className="border border-red-800/60 bg-red-950/20 hover:bg-red-900/40 text-red-400 text-xs font-mono px-2.5 py-1 rounded-md transition inline-flex items-center gap-1 disabled:opacity-60 disabled:cursor-not-allowed"
  >
    <Square className="w-3 h-3 fill-current" />
    Cancel
  </button>
);
