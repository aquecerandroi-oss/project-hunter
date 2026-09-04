/**
 * Applies persisted appearance settings (Settings > Appearance,
 * components/settings/appearance-form.tsx) before first paint, avoiding a
 * flash of the wrong theme/density. Kept as an inline `<script>` in
 * `app/layout.tsx` (not a bundled script) so it runs synchronously before
 * hydration; it only ever reads its own two `localStorage` keys and touches
 * only `data-theme` / `data-density` on `<html>`.
 *
 * Both reads fail open (wrapped in their own `try`/`catch`): a private
 * window, disabled storage, or a stale value never blocks rendering --
 * worst case is that the default theme/density shows instead.
 *
 * `data-density` used to be applied only once `AppearanceForm` mounted
 * (Settings > Appearance itself), so density reset to "comfortable" on any
 * other page until that screen was revisited in the session -- moving the
 * read here (alongside the theme, which already worked this way) is what
 * fixes that.
 */
export const PRE_HYDRATION_SCRIPT = `(function(){
try{var t=localStorage.getItem("hunter-theme");if(t==="light"||t==="dark"){document.documentElement.setAttribute("data-theme",t);}}catch(e){}
try{var d=localStorage.getItem("hunter-density");if(d==="compact"||d==="comfortable"){document.documentElement.setAttribute("data-density",d);}}catch(e){}
})();`;
