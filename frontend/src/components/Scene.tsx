import type { Face } from "../contracts";

/** A quiet garden backdrop. Plant mood stays on the character, not simulated weather. */
export function Scene({ face }: { face: Face }) {
  return <div className={`scene garden-scene scene-${face}`} aria-hidden><div className="garden-halo" /><div className="garden-ground" /></div>;
}
