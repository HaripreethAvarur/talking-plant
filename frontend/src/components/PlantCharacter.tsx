import type { Face } from "../contracts";

interface Look {
  leaf: string;
  leafDark: string;
  face: string;
  animation: string;
  leafTilt: number; // degrees; positive droops the side leaves
}

const LOOKS: Record<Face, Look> = {
  happy: { leaf: "#58b85c", leafDark: "#3e9443", face: "#7ccf6e", animation: "sway", leafTilt: -10 },
  grateful: { leaf: "#4cc35a", leafDark: "#2f9a3e", face: "#86dc76", animation: "bounce", leafTilt: -22 },
  thirsty: { leaf: "#a5b04a", leafDark: "#7f8a33", face: "#b9c46a", animation: "droop", leafTilt: 38 },
  soggy: { leaf: "#4f9e86", leafDark: "#357a66", face: "#7cc2ad", animation: "wobble", leafTilt: 28 },
  too_dark: { leaf: "#3f7f4c", leafDark: "#2c5d37", face: "#5c9a63", animation: "sleepy", leafTilt: 15 },
  sleepy: { leaf: "#4f8a5a", leafDark: "#356843", face: "#6fa878", animation: "sleepy", leafTilt: 5 },
  unwell: { leaf: "#9bab3f", leafDark: "#76832c", face: "#b1bf63", animation: "wobble", leafTilt: 25 },
  offline: { leaf: "#9aa59b", leafDark: "#737d74", face: "#b9c2ba", animation: "still", leafTilt: 12 },
};

const INK = "#2b2b2b";

function Eyes({ face }: { face: Face }) {
  switch (face) {
    case "grateful": // closed, smiling eyes  ^ ^
      return (
        <g stroke={INK} strokeWidth={6} fill="none" strokeLinecap="round">
          <path d="M70 118 q14 -16 28 0" />
          <path d="M142 118 q14 -16 28 0" />
        </g>
      );
    case "sleepy": // closed, peaceful  ‿ ‿
    case "offline":
      return (
        <g stroke={INK} strokeWidth={5} fill="none" strokeLinecap="round">
          <path d="M70 116 q14 12 28 0" />
          <path d="M142 116 q14 12 28 0" />
        </g>
      );
    case "thirsty": // tired, half-closed
    case "too_dark":
      return (
        <g>
          <ellipse cx={84} cy={118} rx={13} ry={face === "too_dark" ? 3 : 7} fill={INK} />
          <ellipse cx={156} cy={118} rx={13} ry={face === "too_dark" ? 3 : 7} fill={INK} />
          <g stroke={INK} strokeWidth={4} strokeLinecap="round">
            <path d="M68 104 l30 6" />
            <path d="M172 104 l-30 6" />
          </g>
        </g>
      );
    case "soggy": // wide, surprised
      return (
        <g>
          <circle cx={84} cy={116} r={15} fill="#fff" stroke={INK} strokeWidth={4} />
          <circle cx={156} cy={116} r={15} fill="#fff" stroke={INK} strokeWidth={4} />
          <circle cx={84} cy={118} r={6} fill={INK} />
          <circle cx={156} cy={118} r={6} fill={INK} />
        </g>
      );
    case "unwell":
      return (
        <g stroke={INK} strokeWidth={5} strokeLinecap="round">
          <path d="M74 108 l20 20 M94 108 l-20 20" />
          <path d="M146 108 l20 20 M166 108 l-20 20" />
        </g>
      );
    default:
      return (
        <g>
          <circle cx={84} cy={116} r={13} fill={INK} />
          <circle cx={156} cy={116} r={13} fill={INK} />
          <circle cx={89} cy={111} r={4} fill="#fff" />
          <circle cx={161} cy={111} r={4} fill="#fff" />
        </g>
      );
  }
}

const MOUTHS: Record<Face, string> = {
  happy: "M96 150 q24 26 48 0",
  grateful: "M90 146 q30 36 60 0",
  thirsty: "M100 164 q20 -14 40 0",
  soggy: "M106 160 q14 -12 28 0 q-14 12 -28 0",
  too_dark: "M104 160 h32",
  sleepy: "M108 158 q12 8 24 0",
  unwell: "M98 160 q8 -8 16 0 q8 8 16 0 q8 -8 12 0",
  offline: "M106 160 h28",
};

function Mouth({ face, speaking, level }: { face: Face; speaking: boolean; level: number }) {
  if (speaking) {
    const open = 4 + level * 18;
    return (
      <g>
        <ellipse cx={120} cy={158} rx={16 + level * 4} ry={open} fill="#6b2a2a" stroke={INK} strokeWidth={4} />
        {open > 10 && <ellipse cx={120} cy={158 + open * 0.45} rx={9} ry={open * 0.35} fill="#e57373" />}
      </g>
    );
  }
  return <path d={MOUTHS[face]} stroke={INK} strokeWidth={6} fill="none" strokeLinecap="round" />;
}

interface Props {
  face: Face;
  speaking: boolean;
  level: number;
}

const DESCRIPTIONS: Record<Face, string> = {
  happy: "happy",
  grateful: "grateful",
  thirsty: "thirsty",
  soggy: "too wet",
  too_dark: "in the dark",
  sleepy: "asleep",
  unwell: "unwell",
  offline: "unable to feel its sensors",
};

/** The plant: one face and body animation per mood, mouth driven by audio level. */
export function PlantCharacter({ face, speaking, level }: Props) {
  const look = LOOKS[face];
  return (
    <svg className={`plant anim-${look.animation}`} viewBox="0 0 240 340" role="img" aria-label={`The plant looks ${DESCRIPTIONS[face]}`}>
      {/* pot */}
      <path d="M58 262 h124 l-12 70 h-100 z" fill="#c8693f" />
      <rect x={50} y={248} width={140} height={22} rx={8} fill="#de7d50" />
      <ellipse cx={120} cy={250} rx={62} ry={7} fill={face === "soggy" ? "#3b5f7a" : "#5a3b26"} />

      <g className="plant-body">
        {/* stem and side leaves */}
        <path d="M120 250 C118 225 122 210 120 190" stroke={look.leafDark} strokeWidth={10} fill="none" strokeLinecap="round" />
        <g style={{ transform: `rotate(${look.leafTilt}deg)`, transformOrigin: "118px 228px", transition: "transform 0.8s" }}>
          <path d="M118 228 C90 200 52 206 34 226 C58 246 96 246 118 228 z" fill={look.leaf} />
          <path d="M118 228 C92 222 66 222 40 226" stroke={look.leafDark} strokeWidth={3} fill="none" />
        </g>
        <g style={{ transform: `rotate(${-look.leafTilt}deg)`, transformOrigin: "122px 228px", transition: "transform 0.8s" }}>
          <path d="M122 228 C150 200 188 206 206 226 C182 246 144 246 122 228 z" fill={look.leaf} />
          <path d="M122 228 C148 222 174 222 200 226" stroke={look.leafDark} strokeWidth={3} fill="none" />
        </g>

        {/* head: a big round leaf with the face */}
        <g className="plant-head">
          <path d="M120 20 C60 30 34 80 36 130 C40 180 80 200 120 200 C160 200 200 180 204 130 C206 80 180 30 120 20 z" fill={look.face} stroke={look.leafDark} strokeWidth={5} style={{ transition: "fill 0.8s" }} />
          <path d="M120 22 C116 10 124 2 134 0" stroke={look.leafDark} strokeWidth={5} fill="none" strokeLinecap="round" />
          {face === "unwell" && (
            <g fill="#a07a2c" opacity={0.55}>
              <circle cx={64} cy={84} r={8} />
              <circle cx={178} cy={150} r={6} />
              <circle cx={170} cy={70} r={5} />
            </g>
          )}
          {(face === "happy" || face === "grateful" || face === "sleepy") && (
            <g fill="#ff8a80" opacity={face === "sleepy" ? 0.35 : 0.55}>
              <ellipse cx={62} cy={146} rx={14} ry={8} />
              <ellipse cx={178} cy={146} rx={14} ry={8} />
            </g>
          )}
          <Eyes face={face} />
          <Mouth face={face} speaking={speaking} level={level} />
          {face === "thirsty" && <path className="sweat" d="M186 92 q8 14 0 20 q-8 -6 0 -20 z" fill="#64b5f6" />}
        </g>
      </g>

      {face === "soggy" && (
        <g className="drips" fill="#4fa3e0">
          <path d="M30 150 q7 12 0 17 q-7 -5 0 -17 z" />
          <path d="M214 120 q7 12 0 17 q-7 -5 0 -17 z" />
          <path d="M200 236 q6 10 0 14 q-6 -4 0 -14 z" />
        </g>
      )}
      {face === "grateful" && (
        <g className="sparkles" fill="#ffca28">
          <path d="M24 60 l5 12 l12 5 l-12 5 l-5 12 l-5 -12 l-12 -5 l12 -5 z" />
          <path d="M212 40 l4 9 l9 4 l-9 4 l-4 9 l-4 -9 l-9 -4 l9 -4 z" />
          <path d="M222 170 l4 9 l9 4 l-9 4 l-4 9 l-4 -9 l-9 -4 l9 -4 z" />
        </g>
      )}
      {face === "sleepy" && (
        <g className="zzz" fill="#5c6bc0" fontWeight={800}>
          <text x={186} y={52} fontSize={30}>z</text>
          <text x={208} y={30} fontSize={22}>z</text>
        </g>
      )}
      {face === "too_dark" && <text x={196} y={44} fontSize={30}>💡</text>}
      {face === "offline" && <text x={190} y={46} fontSize={30}>🔌</text>}
    </svg>
  );
}
