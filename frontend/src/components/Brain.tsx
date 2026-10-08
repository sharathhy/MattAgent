/* eslint-disable @typescript-eslint/no-non-null-assertion -- render loop indexes fixed-length arrays it built itself */
import { useEffect, useRef } from "react";

import type { BrainSignals, VoiceState } from "../voice/VoiceProvider";

/**
 * MATT's brain: a rotating 3D neural mesh shaped like two hemispheres, with synapse pulses
 * racing along its connections, a glowing core, HUD rings and a voice waveform.
 * It reads live mic/voice levels every frame, so it breathes while listening, swirls
 * while thinking and throbs with each spoken word.
 */

interface Palette {
  node: [number, number, number];
  pulse: [number, number, number];
  energy: number;
  spin: number;
  pulses: number;
}

const PALETTES: Record<VoiceState, Palette> = {
  unsupported: { node: [56, 189, 248], pulse: [167, 139, 250], energy: 0.35, spin: 0.08, pulses: 6 },
  idle: { node: [56, 189, 248], pulse: [125, 211, 252], energy: 0.3, spin: 0.08, pulses: 4 },
  off: { node: [100, 116, 139], pulse: [148, 163, 184], energy: 0.15, spin: 0.04, pulses: 1 },
  blocked: { node: [248, 113, 113], pulse: [251, 146, 60], energy: 0.3, spin: 0.05, pulses: 3 },
  sleeping: { node: [34, 211, 238], pulse: [125, 211, 252], energy: 0.5, spin: 0.12, pulses: 10 },
  awake: { node: [103, 232, 249], pulse: [255, 255, 255], energy: 0.9, spin: 0.22, pulses: 24 },
  thinking: { node: [167, 139, 250], pulse: [244, 114, 182], energy: 1, spin: 0.9, pulses: 60 },
  speaking: { node: [45, 212, 191], pulse: [190, 242, 100], energy: 1, spin: 0.25, pulses: 30 },
};

interface Pt {
  x: number;
  y: number;
  z: number;
}

/** Points on a brain-like surface: two flattened, elongated hemispheres with a central fissure. */
function buildMesh(count: number) {
  const pts: Pt[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const th = golden * i;
    let x = Math.cos(th) * r;
    let z = Math.sin(th) * r;
    let yy = y * 0.82;
    // Fissure: push points away from the midline so two hemispheres appear.
    x = x * 0.82 + Math.sign(x || 1) * 0.16;
    // Elongate front-to-back, flatten the base, drop the temporal lobes.
    z *= 1.38;
    if (yy < -0.3) yy = -0.3 + (yy + 0.3) * 0.45;
    if (y < 0.1 && z > -0.2 && z < 0.9) yy -= 0.18 * (1 - Math.abs(z - 0.35) / 0.65) * Math.min(1, Math.abs(x) * 1.6);
    // Frontal lobe a little taller than the occipital.
    yy += 0.06 * Math.max(0, z);
    const fold = 1 + 0.07 * Math.sin(th * 7 + y * 11) + 0.05 * Math.sin(y * 21 + z * 6);
    pts.push({ x: x * fold, y: yy * fold, z: z * fold });
  }
  // Cerebellum: a small dense lobe tucked under the back.
  const small = Math.round(count * 0.12);
  for (let i = 0; i < small; i++) {
    const y = 1 - (i / (small - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const th = golden * i;
    const x = Math.cos(th) * r * 0.62;
    pts.push({ x: x + Math.sign(x || 1) * 0.04, y: -0.5 + y * 0.2, z: -0.95 + Math.sin(th) * r * 0.32 });
  }
  const edges: [number, number][] = [];
  const maxD = 0.3;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i]!;
    let linked = 0;
    for (let j = i + 1; j < pts.length && linked < 4; j++) {
      const b = pts[j]!;
      const d = Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
      if (d < maxD && Math.sign(a.x) === Math.sign(b.x)) {
        edges.push([i, j]);
        linked++;
      }
    }
  }
  // A few long-range "corpus callosum" bridges between hemispheres.
  for (let k = 0; k < 18; k++) {
    const i = Math.floor((k / 18) * pts.length);
    let best = -1;
    let bestD = Infinity;
    for (let j = 0; j < pts.length; j++) {
      const a = pts[i]!;
      const b = pts[j]!;
      if (Math.sign(a.x) === Math.sign(b.x)) continue;
      const d = Math.hypot(a.x + b.x, a.y - b.y, a.z - b.z);
      if (d < bestD) {
        bestD = d;
        best = j;
      }
    }
    if (best >= 0) edges.push([i, best]);
  }
  return { pts, edges };
}

const mix = (a: number[], b: number[], t: number) => a.map((v, i) => v + ((b[i] ?? v) - v) * t);
const rgba = (c: number[], a: number) => `rgba(${c[0]! | 0},${c[1]! | 0},${c[2]! | 0},${a})`;

export function Brain({ state, signals, size = 420, compact = false }: {
  state: VoiceState;
  signals: BrainSignals;
  size?: number;
  compact?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef(state);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const { pts, edges } = buildMesh(compact ? 160 : 380);
    const projected = pts.map(() => ({ x: 0, y: 0, z: 0, s: 1 }));
    const pulses: { e: number; t: number; v: number }[] = [];
    const wave = new Array<number>(96).fill(0);
    let cur = { ...PALETTES[stateRef.current] };
    let rot = 0;
    let level = 0;
    let last = performance.now();
    let raf = 0;

    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const target = PALETTES[stateRef.current];
      const k = Math.min(1, dt * 3);
      cur = {
        node: mix(cur.node, target.node, k) as Palette["node"],
        pulse: mix(cur.pulse, target.pulse, k) as Palette["pulse"],
        energy: cur.energy + (target.energy - cur.energy) * k,
        spin: cur.spin + (target.spin - cur.spin) * k,
        pulses: target.pulses,
      };
      const raw = Math.max(signals.mic(), signals.voice());
      level += (raw - level) * Math.min(1, dt * 12);
      const t = now / 1000;
      const motion = reduced ? 0.25 : 1;
      rot += dt * cur.spin * motion;

      const W = size;
      const cx = W / 2;
      const cy = W / 2;
      const R = W * (compact ? 0.3 : 0.27) * (1 + level * 0.08 + Math.sin(t * 1.6) * 0.012 * cur.energy);
      ctx.clearRect(0, 0, W, W);

      // Core glow.
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.9);
      glow.addColorStop(0, rgba(cur.node, 0.28 * cur.energy + level * 0.25));
      glow.addColorStop(0.45, rgba(cur.pulse, 0.08 * cur.energy));
      glow.addColorStop(1, rgba(cur.node, 0));
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, W, W);

      // Project the mesh: yaw rotation plus a slow nod.
      const cosY = Math.cos(rot);
      const sinY = Math.sin(rot);
      const tilt = 0.32 + Math.sin(t * 0.3) * 0.08;
      const cosX = Math.cos(tilt);
      const sinX = Math.sin(tilt);
      for (let i = 0; i < pts.length; i++) {
        const p = pts[i]!;
        const jitter = 1 + level * 0.06 * Math.sin(t * 9 + i);
        const x1 = (p.x * cosY - p.z * sinY) * jitter;
        const z1 = (p.x * sinY + p.z * cosY) * jitter;
        const y1 = p.y * cosX - z1 * sinX;
        const z2 = p.y * sinX + z1 * cosX;
        const persp = 2.6 / (2.6 + z2);
        const q = projected[i]!;
        q.x = cx + x1 * R * persp;
        q.y = cy + y1 * R * persp;
        q.z = z2;
        q.s = persp;
      }

      // Connections, fading with depth.
      ctx.lineWidth = compact ? 0.6 : 0.7;
      for (const [a, b] of edges) {
        const p = projected[a]!;
        const q = projected[b]!;
        const depth = 0.5 - (p.z + q.z) / 4;
        ctx.strokeStyle = rgba(cur.node, (0.06 + 0.22 * depth) * (0.5 + cur.energy * 0.5));
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(q.x, q.y);
        ctx.stroke();
      }

      // Neurons.
      for (let i = 0; i < projected.length; i++) {
        const q = projected[i]!;
        const depth = 0.5 - q.z / 2;
        const flicker = 0.75 + 0.25 * Math.sin(t * 3 + i * 1.7);
        ctx.fillStyle = rgba(cur.node, (0.25 + 0.75 * depth) * flicker);
        ctx.beginPath();
        ctx.arc(q.x, q.y, (compact ? 0.9 : 1.2) * q.s + depth * 0.8, 0, Math.PI * 2);
        ctx.fill();
      }

      // Synapse pulses travelling along edges.
      const wanted = Math.round(cur.pulses * motion * (compact ? 0.5 : 1));
      while (pulses.length < wanted && edges.length) {
        pulses.push({ e: Math.floor(Math.random() * edges.length), t: 0, v: 0.6 + Math.random() * 1.6 });
      }
      ctx.globalCompositeOperation = "lighter";
      for (let i = pulses.length - 1; i >= 0; i--) {
        const pl = pulses[i]!;
        pl.t += dt * pl.v * (0.6 + cur.energy);
        const edge = edges[pl.e];
        if (pl.t >= 1 || !edge) {
          pulses.splice(i, 1);
          continue;
        }
        const a = projected[edge[0]]!;
        const b = projected[edge[1]]!;
        const x = a.x + (b.x - a.x) * pl.t;
        const y = a.y + (b.y - a.y) * pl.t;
        const g = ctx.createRadialGradient(x, y, 0, x, y, compact ? 4 : 7);
        g.addColorStop(0, rgba(cur.pulse, 0.95));
        g.addColorStop(1, rgba(cur.pulse, 0));
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(x, y, compact ? 4 : 7, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalCompositeOperation = "source-over";

      if (!compact) {
        // HUD rings.
        const rings = [
          { r: R * 1.55, w: 1, dash: [2, 6], speed: 0.15 },
          { r: R * 1.7, w: 2, dash: [40, 14, 6, 14], speed: -0.25 * (1 + cur.energy) },
          { r: R * 1.85, w: 1, dash: [1, 3], speed: 0.08 },
        ];
        for (const ring of rings) {
          ctx.save();
          ctx.translate(cx, cy);
          ctx.rotate(t * ring.speed * motion);
          ctx.setLineDash(ring.dash);
          ctx.strokeStyle = rgba(cur.node, 0.25 + 0.25 * cur.energy);
          ctx.lineWidth = ring.w;
          ctx.beginPath();
          ctx.arc(0, 0, ring.r, 0, Math.PI * 2);
          ctx.stroke();
          ctx.restore();
        }
        ctx.setLineDash([]);
        // Scanning arc while thinking.
        if (stateRef.current === "thinking") {
          ctx.strokeStyle = rgba(cur.pulse, 0.8);
          ctx.lineWidth = 3;
          ctx.beginPath();
          const a0 = t * 4;
          ctx.arc(cx, cy, R * 1.7, a0, a0 + 0.9);
          ctx.stroke();
        }
        // Voice waveform ring.
        for (let i = 0; i < wave.length; i++) {
          const n = Math.sin(t * 7 + i * 0.7) * 0.5 + Math.sin(t * 13 + i * 1.9) * 0.5;
          const amp = level * (0.5 + 0.5 * Math.abs(n));
          wave[i] = wave[i]! + (amp - wave[i]!) * 0.35;
        }
        ctx.strokeStyle = rgba(cur.pulse, Math.min(0.9, 0.08 + level * 1.6));
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let i = 0; i <= wave.length; i++) {
          const idx = i % wave.length;
          const ang = (idx / wave.length) * Math.PI * 2 - Math.PI / 2;
          const rr = R * 1.32 + wave[idx]! * R * 0.35;
          const x = cx + Math.cos(ang) * rr;
          const y = cy + Math.sin(ang) * rr;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [signals, size, compact]);

  return (
    <canvas
      ref={canvasRef}
      role="img"
      aria-label={`MATT brain, ${state}`}
      style={{ width: size, height: size, maxWidth: "100%" }}
      className="block aspect-square h-auto"
    />
  );
}
