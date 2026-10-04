import { useId } from "react";
import type { Face } from "../contracts";

const INK = "#2b1a4a";

/** Head colours (top, bottom of the gradient) per face. */
const SKIN: Record<Face, [string, string]> = {
  happy: ["#9be564", "#45b33a"],
  grateful: ["#a8f06a", "#4cc03d"],
  thirsty: ["#d4d873", "#a5a943"],
  soggy: ["#8be0c2", "#3fae8c"],
  too_dark: ["#78b874", "#3f8446"],
  sleepy: ["#7cbf86", "#428c55"],
  unwell: ["#c5d46f", "#94a640"],
  offline: ["#cfd5d0", "#9ea7a0"],
};

function Eyes({ face, skin }: { face: Face; skin: string }) {
  if (face === "grateful") {
    return (
      <g stroke={INK} strokeWidth={7} fill="none" strokeLinecap="round">
        <path d="M98 150 q18 -22 36 0" />
        <path d="M166 150 q18 -22 36 0" />
      </g>
    );
  }
  if (face === "sleepy" || face === "offline") {
    return (
      <g stroke={INK} strokeWidth={6} fill="none" strokeLinecap="round">
        <path d="M98 148 q18 14 36 0" />
        <path d="M166 148 q18 14 36 0" />
      </g>
    );
  }
  const wide = face === "soggy";
  const lid = face === "thirsty" || face === "unwell" ? 0.5 : face === "too_dark" ? 0.35 : 0;
  const look = face === "too_dark" ? 6 : 0;
  const eye = (cx: number) => (
    <g className="eye">
      <ellipse cx={cx} cy={146} rx={wide ? 22 : 19} ry={wide ? 26 : 23} fill="#fff" stroke={INK} strokeWidth={5} />
      <circle cx={cx + 3 + look} cy={150} r={wide ? 8 : 12} fill={INK} />
      <circle cx={cx + 8 + look} cy={143} r={4.5} fill="#fff" />
      <circle cx={cx - 1 + look} cy={156} r={2} fill="#fff" />
      {lid > 0 && (
        <path
          d={`M${cx - 23} ${146 - 25} h46 v${50 * lid} q-23 8 -46 0 z`}
          fill={skin}
          stroke={INK}
          strokeWidth={5}
          strokeLinejoin="round"
        />
      )}
    </g>
  );
  return (
    <g>
      {eye(116)}
      {eye(184)}
    </g>
  );
}

function Brows({ face }: { face: Face }) {
  const shapes: Partial<Record<Face, [string, string]>> = {
    thirsty: ["M96 118 q18 -4 38 -14", "M204 118 q-18 -4 -38 -14"], // worried: inner ends up
    soggy: ["M98 104 q18 -12 36 0", "M166 104 q18 -12 36 0"],
    unwell: ["M98 118 q9 -8 18 0 q9 8 18 0", "M166 118 q9 -8 18 0 q9 8 18 0"],
    too_dark: ["M100 114 l32 -4", "M168 110 l32 4"],
  };
  const brow = shapes[face];
  if (!brow) return null;
  return (
    <g stroke={INK} strokeWidth={6} fill="none" strokeLinecap="round">
      <path d={brow[0]} />
      <path d={brow[1]} />
    </g>
  );
}

function Mouth({ face, speaking, level }: { face: Face; speaking: boolean; level: number }) {
  if (speaking) {
    const open = 6 + level * 22;
    return (
      <g>
        <ellipse cx={150} cy={196} rx={20 + level * 6} ry={open} fill="#7a1f3d" stroke={INK} strokeWidth={5} />
        {open > 12 && <ellipse cx={150} cy={196 + open * 0.45} rx={11} ry={open * 0.38} fill="#ff6f91" />}
      </g>
    );
  }
  switch (face) {
    case "happy":
    case "grateful": {
      const w = face === "grateful" ? 40 : 32;
      return (
        <g>
          <path d={`M${150 - w} 184 q${w} ${w * 1.4} ${w * 2} 0 z`} fill="#7a1f3d" stroke={INK} strokeWidth={5} strokeLinejoin="round" />
          <path d={`M${150 - w * 0.5} ${184 + w * 0.42} q${w * 0.5} -10 ${w} 0 q-${w * 0.5} ${w * 0.25} -${w} 0`} fill="#ff6f91" />
        </g>
      );
    }
    case "thirsty":
      return (
        <g>
          <ellipse cx={150} cy={198} rx={15} ry={12} fill="#7a1f3d" stroke={INK} strokeWidth={5} />
          <path d="M140 202 q10 22 20 0 z" fill="#ff6f91" stroke={INK} strokeWidth={4} />
        </g>
      );
    case "too_dark":
      return <ellipse cx={150} cy={198} rx={9} ry={11} fill="#7a1f3d" stroke={INK} strokeWidth={5} />;
    case "soggy":
      return <path d="M126 200 q8 -10 16 0 q8 10 16 0 q8 -10 16 0" stroke={INK} strokeWidth={6} fill="none" strokeLinecap="round" />;
    case "unwell":
      return <path d="M130 206 q20 -18 40 0" stroke={INK} strokeWidth={6} fill="none" strokeLinecap="round" />;
    case "sleepy":
      return <path d="M138 194 q12 10 24 0" stroke={INK} strokeWidth={6} fill="none" strokeLinecap="round" />;
    default:
      return <path d="M136 198 h28" stroke={INK} strokeWidth={6} strokeLinecap="round" />;
  }
}

interface Props {
  face: Face;
  speaking: boolean;
  level: number;
  listening?: boolean;
}

const DESCRIPTIONS: Record<Face, string> = {
  happy: "happy",
  grateful: "very grateful",
  thirsty: "thirsty",
  soggy: "too wet",
  too_dark: "in the dark",
  sleepy: "asleep",
  unwell: "unwell",
  offline: "unable to feel its sensors",
};

/** The plant mascot: a glossy round head with a sprout, leaf arms and a polka-dot pot. */
export function PlantCharacter({ face, speaking, level, listening }: Props) {
  const [top, bottom] = SKIN[face];
  const uid = useId().replace(/:/g, "");
  const skinId = `skin-${uid}`;
  const skin = `url(#${skinId})`;
  const potId = `pot-${uid}`;
  const soil = face === "soggy" ? "#3d4f6b" : face === "thirsty" ? "#b98a5a" : "#5b3a24";
  return (
    <svg
      className={`character face-${face} ${speaking ? "is-speaking" : ""} ${listening ? "is-listening" : ""}`}
      viewBox="0 0 300 380"
      role="img"
      aria-label={`The plant looks ${DESCRIPTIONS[face]}`}
    >
      <defs>
        <linearGradient id={skinId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={top} />
          <stop offset="100%" stopColor={bottom} />
        </linearGradient>
        <linearGradient id={potId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ff8a5b" />
          <stop offset="100%" stopColor="#f2574a" />
        </linearGradient>
      </defs>

      <ellipse className="ground-shadow" cx={150} cy={366} rx={92} ry={11} fill="rgba(43,26,74,0.22)" />

      <g className="char-body">
        {/* pot */}
        <g className="pot">
          <path d="M84 276 h132 l-14 84 q-2 10 -12 10 h-80 q-10 0 -12 -10 z" fill={`url(#${potId})`} stroke={INK} strokeWidth={6} strokeLinejoin="round" />
          <g fill="#fff" opacity={0.85}>
            <circle cx={112} cy={312} r={6} />
            <circle cx={150} cy={330} r={7} />
            <circle cx={188} cy={310} r={6} />
            <circle cx={130} cy={350} r={4} />
            <circle cx={172} cy={350} r={4} />
          </g>
          <rect x={74} y={258} width={152} height={30} rx={14} fill="#ffb347" stroke={INK} strokeWidth={6} />
          <ellipse cx={150} cy={262} rx={66} ry={8} fill={soil} />
        </g>

        {/* stem and leaf arms */}
        <path d="M150 262 C148 246 152 236 150 222" stroke={INK} strokeWidth={16} fill="none" strokeLinecap="round" />
        <path d="M150 262 C148 246 152 236 150 222" stroke={bottom} strokeWidth={8} fill="none" strokeLinecap="round" />
        <g className="arm arm-left">
          <path d="M146 244 C118 214 76 220 58 240 C84 262 124 262 146 244 z" fill={skin} stroke={INK} strokeWidth={5} strokeLinejoin="round" />
          <path d="M140 244 C116 236 90 236 66 240" stroke={INK} strokeWidth={3} fill="none" opacity={0.5} />
        </g>
        <g className="arm arm-right">
          <path d="M154 244 C182 214 224 220 242 240 C216 262 176 262 154 244 z" fill={skin} stroke={INK} strokeWidth={5} strokeLinejoin="round" />
          <path d="M160 244 C184 236 210 236 234 240" stroke={INK} strokeWidth={3} fill="none" opacity={0.5} />
        </g>

        {/* head */}
        <g className="head">
          <g className="sprout">
            <path d="M150 44 C150 30 152 22 150 12" stroke={INK} strokeWidth={6} fill="none" strokeLinecap="round" />
            <path d="M150 20 C132 2 110 6 104 18 C118 30 138 30 150 20 z" fill={skin} stroke={INK} strokeWidth={5} strokeLinejoin="round" />
            <path d="M150 20 C168 2 190 6 196 18 C182 30 162 30 150 20 z" fill={skin} stroke={INK} strokeWidth={5} strokeLinejoin="round" />
          </g>
          <path d="M150 40 C82 40 52 92 54 146 C56 200 98 228 150 228 C202 228 244 200 246 146 C248 92 218 40 150 40 z" fill={skin} stroke={INK} strokeWidth={6} />
          <ellipse cx={104} cy={86} rx={26} ry={14} fill="#fff" opacity={0.35} transform="rotate(-28 104 86)" />
          {face !== "offline" && face !== "unwell" && (
            <g fill="#ff7aa8" opacity={face === "sleepy" ? 0.4 : 0.6}>
              <ellipse cx={86} cy={186} rx={16} ry={9} />
              <ellipse cx={214} cy={186} rx={16} ry={9} />
            </g>
          )}
          <Brows face={face} />
          <Eyes face={face} skin={skin} />
          <Mouth face={face} speaking={speaking} level={level} />
          {face === "thirsty" && <path className="sweat" d="M230 104 q10 16 0 24 q-10 -8 0 -24 z" fill="#5cc8ff" stroke={INK} strokeWidth={3} />}
          {face === "unwell" && (
            <g transform="rotate(-24 206 92)">
              <rect x={184} y={84} width={44} height={16} rx={7} fill="#ffd8a8" stroke={INK} strokeWidth={4} />
              <rect x={200} y={84} width={12} height={16} fill="#f5b97a" />
            </g>
          )}
          {face === "sleepy" && (
            <g className="zzz" fill="#fff" stroke={INK} strokeWidth={3} fontWeight={700} fontFamily="inherit">
              <text x={222} y={70} fontSize={34}>Z</text>
              <text x={250} y={40} fontSize={26}>z</text>
              <text x={272} y={16} fontSize={20}>z</text>
            </g>
          )}
          {face === "soggy" && (
            <g className="drip" fill="#5cc8ff" stroke={INK} strokeWidth={3}>
              <path d="M66 120 q8 13 0 19 q-8 -6 0 -19 z" />
              <path d="M236 160 q7 11 0 16 q-7 -5 0 -16 z" />
            </g>
          )}
        </g>
      </g>
    </svg>
  );
}
