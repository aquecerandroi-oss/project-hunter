import { MEME_DESK_LABEL } from "@/lib/api/meme-desk-types";

/**
 * Contract §Tela: the permanent, visible label. Rendered from the constant
 * the API also sends (`DeskListOut.label`) -- one string, two places, never
 * a softer paraphrase on screen. `warning` tone, not red: it is a fact
 * about the whole screen, not an error.
 */
export function PaperLabel() {
  return (
    <p role="note" className="rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-xs font-medium text-warning">
      {MEME_DESK_LABEL}
    </p>
  );
}
