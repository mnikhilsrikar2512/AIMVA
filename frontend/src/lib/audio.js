import { useEffect } from "react";

/**
 * While `active`, read the microphone loudness into `levelRef.current` (0..1) using the Web Audio API.
 * Runs alongside SpeechRecognition (it opens its own stream) and releases the mic when inactive.
 */
export function useMicLevel(active, levelRef) {
  useEffect(() => {
    if (!active || !navigator.mediaDevices?.getUserMedia) return;
    let stream, ctx, raf, stopped = false;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
        if (stopped) return stream.getTracks().forEach((t) => t.stop());
        ctx = new (window.AudioContext || window.webkitAudioContext)();
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        ctx.createMediaStreamSource(stream).connect(analyser);
        const buf = new Uint8Array(analyser.fftSize);
        const tick = () => {
          analyser.getByteTimeDomainData(buf);
          let sum = 0;
          for (let i = 0; i < buf.length; i++) {
            const v = (buf[i] - 128) / 128;
            sum += v * v;
          }
          const rms = Math.sqrt(sum / buf.length);
          levelRef.current = Math.min(1, rms * 6); // speech RMS is small; scale into 0..1
          raf = requestAnimationFrame(tick);
        };
        tick();
      } catch {
        /* mic blocked: the orb still reacts to agent speech and sentiment */
      }
    })();
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
      ctx?.close().catch(() => {});
      levelRef.current = 0;
    };
  }, [active, levelRef]);
}

/**
 * Speak `text` (when `voiceOn`) and pulse `levelRef` in rhythm with it.
 * Word-boundary events drive the pulses where the browser supports them; a timer fills the gaps
 * (and simulates the rhythm entirely when speech is muted). Resolves when finished.
 */
export function speakWithPulse(text, { voiceOn, lang, levelRef, onStart, onEnd }) {
  const synth = window.speechSynthesis;
  const started = Date.now();
  const mutedDuration = Math.min(6000, 400 + text.length * 45);
  let timer;
  const finish = () => {
    clearInterval(timer);
    levelRef.current = 0;
    onEnd?.();
  };
  onStart?.();
  timer = setInterval(() => {
    const speaking = voiceOn && synth ? synth.speaking || Date.now() - started < 600 : Date.now() - started < mutedDuration;
    if (!speaking) return finish();
    levelRef.current = Math.max(levelRef.current, 0.35 + Math.random() * 0.55);
  }, 170);
  if (voiceOn && synth) {
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang;
    u.onboundary = () => { levelRef.current = 1; };
    u.onerror = finish;
    synth.speak(u);
  }
  return () => { clearInterval(timer); synth?.cancel(); levelRef.current = 0; };
}
