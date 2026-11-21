// Real, lit 3D things drifting in the hero sky (owner 2026-11-21: flat app cards looked raw and too much like a
// competitor). Each object stands for one part of AIMVA's job, as a physical thing rather than a screenshot:
// a megaphone (your ad), a glass chat bubble (the reply in seconds), a phone (the call back), a map pin (leads near
// you), a flyer (your page) and gold rupee coins (the sale). Materials are lit by a soft studio environment, so glass,
// gold and glossy plastic read as real. Loaded only on laptops and tablets, only while the hero is on screen.
import { useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

const CYAN = "#22C7D4", TEAL = "#0B6B67", MARIGOLD = "#F2A33A", INK = "#0f282f";

function texture(w, h, draw) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}
const font = (px, weight = 600, family = "Inter, system-ui, sans-serif") => `${weight} ${px}px ${family}`;
function round(g, x, y, w, h, r) { g.beginPath(); g.roundRect(x, y, w, h, r); }

function Env() {
  const { gl, scene } = useThree();
  useEffect(() => {
    const pm = new THREE.PMREMGenerator(gl);  // soft studio light for reflections
    const env = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = env;
    return () => { env.dispose(); pm.dispose(); scene.environment = null; };
  }, [gl, scene]);
  return null;
}

/** A thing that floats: bobs, turns slowly, leans toward the pointer and leaves upward as the page scrolls. */
function Float({ at, depth, spin = 0.25, tilt = [0, 0, 0], scroll, pointer, children }) {
  const ref = useRef();
  const seed = useMemo(() => Math.random() * 10, []);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime + seed, s = scroll.current, p = pointer.current, g = ref.current;
    if (!g) return;
    g.position.set(
      at[0] + p.x * 0.5 * depth + Math.sign(at[0] || 1) * s * (1.5 + depth * 3),
      at[1] + Math.sin(t * 0.8) * 0.12 * depth - p.y * 0.35 * depth + s * (3 + depth * 5),
      at[2]);
    g.rotation.set(tilt[0] + Math.sin(t * 0.5) * 0.12, tilt[1] + t * spin * 0.3 + p.x * 0.3, tilt[2] + Math.cos(t * 0.4) * 0.08 + s * 0.6);
  });
  return <group ref={ref}>{children}</group>;
}

function Coin({ r = 0.55 }) {
  const face = useMemo(() => texture(512, 512, (g, w) => {
    const grd = g.createRadialGradient(w * 0.38, w * 0.32, 20, w / 2, w / 2, w / 2);
    grd.addColorStop(0, "#FFE7A8"); grd.addColorStop(0.55, "#F2B24A"); grd.addColorStop(1, "#C27A12");
    g.fillStyle = grd; g.fillRect(0, 0, w, w);
    g.strokeStyle = "rgba(122,67,0,0.55)"; g.lineWidth = 14; g.beginPath(); g.arc(w / 2, w / 2, w * 0.4, 0, Math.PI * 2); g.stroke();
    g.fillStyle = "rgba(122,67,0,0.85)"; g.font = font(300, 700, "Georgia, serif"); g.textAlign = "center"; g.textBaseline = "middle"; g.fillText("₹", w / 2, w / 2 + 14);
  }), []);
  // The faces are flat discs laid on the cylinder, so the ₹ always reads upright from the front and the back.
  const t = r * 0.08 + 0.002;
  return (
    <group>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[r, r, r * 0.16, 64]} />
        <meshPhysicalMaterial color="#E39A2B" metalness={1} roughness={0.28} />
      </mesh>
      <mesh position={[0, 0, t]}><circleGeometry args={[r * 0.98, 64]} /><meshPhysicalMaterial map={face} metalness={0.85} roughness={0.3} clearcoat={0.6} /></mesh>
      <mesh position={[0, 0, -t]} rotation={[0, Math.PI, 0]}><circleGeometry args={[r * 0.98, 64]} /><meshPhysicalMaterial map={face} metalness={0.85} roughness={0.3} clearcoat={0.6} /></mesh>
    </group>
  );
}

function Bubble() {
  const geo = useMemo(() => new RoundedBoxGeometry(2.2, 1.05, 0.34, 6, 0.4), []);
  const words = useMemo(() => texture(1024, 480, (g, w, h) => {
    g.clearRect(0, 0, w, h);
    g.fillStyle = INK; g.font = font(78, 600); g.fillText("Yes! 11 am or 4 pm?", 80, 215);
    g.fillStyle = "#3d6b70"; g.font = font(50, 500); g.fillText("replied in 8 seconds  ✓✓", 80, 320);
  }), []);
  return (
    <group>
      <mesh geometry={geo}>
        <meshPhysicalMaterial color="#d8fbf2" transmission={0.92} thickness={0.6} roughness={0.12} ior={1.4} clearcoat={1} attenuationColor="#9be8dc" attenuationDistance={2} />
      </mesh>
      <mesh position={[0.72, -0.62, 0]} rotation={[0, 0, Math.PI / 4]}>
        <boxGeometry args={[0.32, 0.32, 0.3]} />
        <meshPhysicalMaterial color="#d8fbf2" transmission={0.92} thickness={0.5} roughness={0.12} clearcoat={1} />
      </mesh>
      <mesh position={[0, 0, 0.18]}><planeGeometry args={[2.05, 0.96]} /><meshBasicMaterial map={words} transparent toneMapped={false} /></mesh>
    </group>
  );
}

function Phone() {
  const body = useMemo(() => new RoundedBoxGeometry(1.15, 2.3, 0.12, 6, 0.16), []);
  const screen = useMemo(() => texture(460, 920, (g, w, h) => {
    g.fillStyle = "#0f2a30"; g.fillRect(0, 0, w, h);
    const grd = g.createRadialGradient(w / 2, h * 0.36, 10, w / 2, h * 0.36, 260);
    grd.addColorStop(0, "rgba(94,230,240,0.45)"); grd.addColorStop(1, "rgba(94,230,240,0)"); g.fillStyle = grd; g.fillRect(0, 0, w, h);
    g.fillStyle = "#5EE6F0"; g.beginPath(); g.arc(w / 2, h * 0.36, 70, 0, Math.PI * 2); g.fill();
    g.fillStyle = INK; g.font = font(72, 700); g.textAlign = "center"; g.fillText("☎", w / 2, h * 0.36 + 26);
    g.fillStyle = "#fff"; g.font = font(40, 600); g.fillText("Calling Lakshmi", w / 2, h * 0.56);
    g.fillStyle = "rgba(255,255,255,0.65)"; g.font = font(30, 500); g.fillText("back · 0:14", w / 2, h * 0.61);
    g.fillStyle = "#5EE6F0";
    [0.5, 0.9, 0.6, 1, 0.7, 0.45, 0.85, 0.55, 0.75, 0.5].forEach((v, i) => { const bh = v * 90; round(g, 70 + i * 33, h * 0.74 - bh / 2, 16, bh, 8); g.fill(); });
  }), []);
  return (
    <group>
      <mesh geometry={body}><meshPhysicalMaterial color="#1b2b30" metalness={0.6} roughness={0.25} clearcoat={1} clearcoatRoughness={0.1} /></mesh>
      <mesh position={[0, 0, 0.065]}><planeGeometry args={[1.02, 2.12]} /><meshPhysicalMaterial map={screen} roughness={0.08} clearcoat={1} emissive="#ffffff" emissiveMap={screen} emissiveIntensity={0.35} /></mesh>
    </group>
  );
}

function Megaphone() {
  return (
    <group rotation={[0, 0, -0.5]}>
      <mesh position={[0.45, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
        <cylinderGeometry args={[0.62, 0.22, 0.95, 48, 1, true]} />
        <meshPhysicalMaterial color={CYAN} roughness={0.22} clearcoat={1} side={THREE.DoubleSide} />
      </mesh>
      <mesh position={[0.93, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
        <torusGeometry args={[0.6, 0.05, 16, 64]} />
        <meshPhysicalMaterial color="#ffffff" roughness={0.2} clearcoat={1} />
      </mesh>
      <mesh position={[-0.15, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.24, 0.24, 0.38, 32]} />
        <meshPhysicalMaterial color={TEAL} roughness={0.3} clearcoat={0.8} />
      </mesh>
      <mesh position={[-0.12, -0.38, 0]} rotation={[0, 0, 0.15]}>
        <boxGeometry args={[0.16, 0.5, 0.18]} />
        <meshPhysicalMaterial color={TEAL} roughness={0.3} clearcoat={0.8} />
      </mesh>
    </group>
  );
}

function Pin() {
  return (
    <group>
      <mesh position={[0, 0.25, 0]}><sphereGeometry args={[0.42, 48, 48]} /><meshPhysicalMaterial color="#E8891C" roughness={0.3} clearcoat={0.7} /></mesh>
      <mesh position={[0, -0.25, 0]} rotation={[Math.PI, 0, 0]}><coneGeometry args={[0.36, 0.7, 48]} /><meshPhysicalMaterial color="#E8891C" roughness={0.3} clearcoat={0.7} /></mesh>
      <mesh position={[0, 0.25, 0.36]}><sphereGeometry args={[0.15, 32, 32]} /><meshPhysicalMaterial color="#ffffff" roughness={0.2} /></mesh>
    </group>
  );
}

function Flyer() {
  const geo = useMemo(() => new RoundedBoxGeometry(1.5, 2, 0.03, 2, 0.04), []);
  const face = useMemo(() => texture(600, 800, (g, w, h) => {
    g.fillStyle = "#fffdf8"; g.fillRect(0, 0, w, h);
    const grd = g.createLinearGradient(0, 0, w, h * 0.55); grd.addColorStop(0, TEAL); grd.addColorStop(1, "#5EE6F0");
    g.fillStyle = grd; g.fillRect(36, 36, w - 72, h * 0.5);
    g.fillStyle = "#fff"; g.font = font(64, 500, "Georgia, serif"); g.fillText("Free check-up", 70, 210); g.fillText("this Saturday", 70, 290);
    g.fillStyle = INK; g.font = font(34, 700); g.fillText("Smile Studio Dental", 50, h * 0.66);
    g.fillStyle = "rgba(15,40,47,0.25)"; [0.72, 0.76].forEach((y, i) => { round(g, 50, h * y, i ? 380 : 480, 16, 8); g.fill(); });
    g.fillStyle = MARIGOLD; round(g, 50, h * 0.84, 250, 70, 35); g.fill();
    g.fillStyle = "#2b1700"; g.font = font(32, 700); g.fillText("Book a visit", 82, h * 0.84 + 46);
  }), []);
  return (
    <mesh geometry={geo}>
      <meshPhysicalMaterial attach="material" map={face} roughness={0.55} sheen={0.5} />
    </mesh>
  );
}

const THINGS = [
  { C: Megaphone, at: [-5.6, 1.2, -1.2], depth: 0.7, tilt: [0.2, 0.6, 0.1], s: 1.05 },
  { C: Bubble, at: [4.5, 1.4, -0.4], depth: 0.9, tilt: [0.1, -0.35, 0.05], s: 0.95 },
  { C: Phone, at: [-4.6, -1.8, -0.8], depth: 0.8, tilt: [0.12, 0.22, -0.18], s: 0.9 },
  { C: Pin, at: [4.2, -1.9, 0.2], depth: 1, tilt: [0.2, 0, 0.3], s: 0.9 },
  { C: Flyer, at: [-4.2, 3.4, -3.2], depth: 0.4, tilt: [0.15, 0.25, -0.2], s: 1 },
  { C: Coin, at: [2.3, 3.0, -2.2], depth: 0.5, tilt: [0.3, 0.2, 0.4], s: 1 },
  { C: () => <Coin r={0.35} />, at: [-6.2, -0.2, -3], depth: 0.35, tilt: [0.5, 0.3, 0.2], s: 1 },
  { C: () => <Coin r={0.42} />, at: [1.9, -3.0, -1], depth: 0.6, tilt: [-0.4, 0.2, 0.5], s: 1 },
];

function Rig({ pointer }) {
  const { camera, size } = useThree();
  useFrame(() => {
    // Wider screens see the full field; narrower ones pull the camera back so nothing crowds the words.
    const z = size.width < 1100 ? 12.5 : 10.5;
    camera.position.z += (z - camera.position.z) * 0.1;
    camera.position.x += (pointer.current.x * 0.3 - camera.position.x) * 0.05;
    camera.lookAt(0, 0, 0);
  });
  return null;
}

export default function SkyObjects3D({ scroll, pointer, active = true }) {
  return (
    <Canvas aria-hidden className="!absolute inset-0" dpr={[1, 2]} frameloop={active ? "always" : "never"}
      camera={{ position: [0, 0, 10.5], fov: 42 }} gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      onCreated={({ gl }) => { gl.toneMapping = THREE.ACESFilmicToneMapping; gl.toneMappingExposure = 0.95; }}>
      <Env />
      <hemisphereLight args={["#cfeeff", "#ffe2b8", 0.7]} />
      <directionalLight position={[4, 6, 5]} intensity={1.6} color="#fff6e8" />
      <Rig pointer={pointer} />
      {THINGS.map(({ C, at, depth, tilt, s }, i) => (
        <Float key={i} at={at} depth={depth} tilt={tilt} scroll={scroll} pointer={pointer}>
          <group scale={s}><C /></group>
        </Float>
      ))}
    </Canvas>
  );
}
