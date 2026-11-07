import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

/*
 * Voice agent orb. It carries two live signals so the user can read the call at a glance:
 *  - motion = who is talking and how loudly (mic level while listening, word pulses while speaking)
 *  - colour = caller sentiment (green calm → amber neutral → red upset), blended smoothly
 * `level` is a ref ({ current: 0..1 }) so audio updates never re-render React.
 */

export const SENTIMENT_COLORS = { calm: "#34d399", neutral: "#fbbf24", upset: "#f43f5e", idle: "#8b7bff" };

export function sentimentColor(s) {
  if (s == null) return new THREE.Color(SENTIMENT_COLORS.idle);
  const calm = new THREE.Color(SENTIMENT_COLORS.calm);
  const neutral = new THREE.Color(SENTIMENT_COLORS.neutral);
  const upset = new THREE.Color(SENTIMENT_COLORS.upset);
  const t = Math.max(-1, Math.min(1, s));
  return t >= 0 ? neutral.lerp(calm, Math.min(1, t / 0.5)) : neutral.lerp(upset, Math.min(1, -t / 0.5));
}

// Ashima 3D simplex noise (MIT) for organic surface displacement.
const NOISE = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0);const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy));vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);vec3 l=1.0-g;vec3 i1=min(g.xyz,l.zxy);vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;vec3 x2=x0-i2+C.yyy;vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857;vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);vec4 x_=floor(j*ns.z);vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy;vec4 y=y_*ns.x+ns.yyyy;vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0;vec4 s1=floor(b1)*2.0+1.0;vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);vec3 p1=vec3(a0.zw,h.y);vec3 p2=vec3(a1.xy,h.z);vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`;

const vertexShader = /* glsl */ `
uniform float uTime; uniform float uLevel; uniform float uSwirl;
varying vec3 vNormal; varying vec3 vView; varying float vDisp;
${NOISE}
void main(){
  vec3 p = position;
  float slow = snoise(p * 1.2 + vec3(uTime * 0.25));
  float fast = snoise(p * 2.3 + vec3(uTime * (0.8 + uSwirl * 2.0)));
  float d = slow * (0.06 + uSwirl * 0.08) + fast * uLevel * 0.22;
  vDisp = d;
  p += normal * d;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  vNormal = normalize(normalMatrix * normal);
  vView = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}`;

const fragmentShader = /* glsl */ `
uniform vec3 uColor; uniform float uLevel;
varying vec3 vNormal; varying vec3 vView; varying float vDisp;
void main(){
  float fres = pow(1.0 - max(dot(vNormal, vView), 0.0), 2.2);
  vec3 core = uColor * (0.75 + vDisp * 1.4);
  vec3 col = core + uColor * fres * (1.1 + uLevel * 1.4) + vec3(1.0) * pow(fres, 6.0) * 0.35;
  gl_FragColor = vec4(col, 1.0);
}`;

function Orb({ level, state, sentiment, animate }) {
  const mesh = useRef();
  const halo = useRef();
  const ring = useRef();
  const smooth = useRef(0);
  const target = useMemo(() => new THREE.Color(), []);
  const uniforms = useMemo(() => ({
    uTime: { value: 0 }, uLevel: { value: 0 }, uSwirl: { value: 0 },
    uColor: { value: sentimentColor(null) },
  }), []);

  useFrame((_, dt) => {
    const time = uniforms.uTime.value + (animate ? dt : 0);
    uniforms.uTime.value = time;
    // Ease the audio level so motion feels physical rather than jittery.
    const raw = state === "listening" || state === "speaking" ? level.current : 0;
    smooth.current += (raw - smooth.current) * Math.min(1, dt * (raw > smooth.current ? 18 : 5));
    if (state === "speaking") level.current *= Math.pow(0.04, dt); // word pulses decay between boundaries
    const breathe = state === "idle" || state === "ended" ? 0.04 * Math.sin(time * 1.6) : 0;
    uniforms.uLevel.value = animate ? smooth.current : 0;
    uniforms.uSwirl.value += ((state === "thinking" ? 1 : 0) - uniforms.uSwirl.value) * Math.min(1, dt * 4);

    target.copy(sentimentColor(state === "ended" && sentiment == null ? null : sentiment));
    uniforms.uColor.value.lerp(target, Math.min(1, dt * 2.5));

    const s = 1 + breathe + smooth.current * 0.12;
    mesh.current.scale.setScalar(s);
    mesh.current.rotation.y += dt * (0.15 + uniforms.uSwirl.value * 1.2) * (animate ? 1 : 0);
    halo.current.scale.setScalar(1.35 + smooth.current * 0.45 + breathe);
    halo.current.material.color.copy(uniforms.uColor.value);
    halo.current.material.opacity = 0.12 + smooth.current * 0.16;
    ring.current.rotation.z += dt * (0.3 + uniforms.uSwirl.value * 2.5) * (animate ? 1 : 0);
    ring.current.material.color.copy(uniforms.uColor.value);
    ring.current.material.opacity = state === "thinking" ? 0.7 : 0.25;
  });

  return (
    <group>
      <mesh ref={halo}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshBasicMaterial transparent depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh ref={mesh}>
        <icosahedronGeometry args={[1, 48]} />
        <shaderMaterial vertexShader={vertexShader} fragmentShader={fragmentShader} uniforms={uniforms} />
      </mesh>
      <mesh ref={ring} rotation={[Math.PI / 2.3, 0.2, 0]}>
        <torusGeometry args={[1.55, 0.012, 8, 128, Math.PI * 1.4]} />
        <meshBasicMaterial transparent toneMapped={false} />
      </mesh>
    </group>
  );
}

export function hasWebGL() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch {
    return false;
  }
}

// Flat fallback: same signals (scale = level, colour = sentiment) with CSS only.
function FlatOrb({ level, state, sentiment }) {
  const el = useRef(null);
  useEffect(() => {
    let raf;
    const tick = () => {
      if (el.current) {
        const l = state === "listening" || state === "speaking" ? level.current : 0;
        if (state === "speaking") level.current *= 0.93;
        el.current.style.transform = `scale(${1 + l * 0.15})`;
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, [level, state]);
  const c = `#${sentimentColor(sentiment).getHexString()}`;
  return (
    <div className="grid h-full w-full place-items-center">
      <div ref={el} className="size-40 rounded-full transition-[background] duration-700"
        style={{ background: `radial-gradient(circle at 35% 30%, #fff, ${c} 45%, ${c}cc 75%)`, boxShadow: `0 20px 60px ${c}55` }} />
    </div>
  );
}

export default function VoiceOrb({ level, state = "idle", sentiment = null, className }) {
  const [webgl, setWebgl] = useState(hasWebGL);
  const reduceMotion = useMemo(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches, []);
  return (
    <div className={className} aria-hidden>
      {webgl ? (
        <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }} dpr={[1, 2]} gl={{ alpha: true, antialias: true, powerPreference: "low-power" }}
          // If the GPU drops the context (driver reset, too many tabs), fall back to the CSS orb instead of a blank box.
          onCreated={({ gl }) => gl.domElement.addEventListener("webglcontextlost", () => setWebgl(false), { once: true })}>
          <Orb level={level} state={state} sentiment={sentiment} animate={!reduceMotion} />
        </Canvas>
      ) : (
        <FlatOrb level={level} state={state} sentiment={sentiment} />
      )}
    </div>
  );
}
