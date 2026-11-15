import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Lock, Pause, Play } from "lucide-react";
import { cx } from "./ui";

/*
 * Animated "how your ad will look" preview. Placements come from the accounts the user has
 * connected (Meta → Facebook, Instagram feed & Story; Google → Search; LinkedIn → feed), so the
 * preview always answers "where will this actually run?". Each placement copies the real app's
 * screen (app bar, post layout, action row, tab bar, type sizes and colours) so what people see
 * here is what their customers will see.
 */

export const PLACEMENTS = [
  { key: "facebook", label: "Facebook feed", provider: "meta" },
  { key: "instagram", label: "Instagram feed", provider: "meta" },
  { key: "story", label: "Instagram Story", provider: "meta", dark: true },
  { key: "google", label: "Google Search", provider: "google", still: true },
  { key: "linkedin", label: "LinkedIn feed", provider: "linkedin" },
];
const PROVIDER_LABEL = { meta: "Meta", google: "Google", linkedin: "LinkedIn" };
const DWELL_MS = 4200;
const SYSTEM_FONT = { fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif' };

// ---- shared glyphs (drawn to match each app's own icon set) --------------------------------------------
const I = ({ d, size = 24, className, fill = "none", sw = 2, children }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke={fill === "none" ? "currentColor" : "none"} strokeWidth={sw}
    strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>{d ? <path d={d} /> : children}</svg>
);
const Dots = ({ className }) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /></svg>
);
const Globe = () => (
  <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor" aria-hidden><path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0Zm5.9 7.2h-2.5a12.5 12.5 0 0 0-1-4.9 6.4 6.4 0 0 1 3.5 4.9ZM8 14.4c-.7 0-1.9-2.2-2-5.6h4c-.1 3.4-1.3 5.6-2 5.6ZM6 7.2c.1-3.4 1.3-5.6 2-5.6s1.9 2.2 2 5.6H6ZM5.6 2.3a12.5 12.5 0 0 0-1 4.9H2.1a6.4 6.4 0 0 1 3.5-4.9ZM2.1 8.8h2.5a12.5 12.5 0 0 0 1 4.9 6.4 6.4 0 0 1-3.5-4.9Zm8.3 4.9a12.5 12.5 0 0 0 1-4.9h2.5a6.4 6.4 0 0 1-3.5 4.9Z" /></svg>
);

function Avatar({ brand, logo, size = 32, square, ring }) {
  const inner = logo
    ? <img src={logo} alt="" className={cx("size-full bg-white object-contain", square ? "rounded" : "rounded-full")} />
    : <span className={cx("grid size-full place-items-center bg-gradient-to-br from-indigo-500 to-cyan-400 font-bold text-white", square ? "rounded" : "rounded-full")}
      style={{ fontSize: size * 0.42 }}>{(brand || "A")[0].toUpperCase()}</span>;
  if (!ring) return <span className="block shrink-0" style={{ width: size, height: size }}>{inner}</span>;
  return (
    <span className="block shrink-0 rounded-full bg-[conic-gradient(from_200deg,#feda75,#fa7e1e,#d62976,#962fbf,#4f5bd5,#feda75)] p-[2px]" style={{ width: size + 6, height: size + 6 }}>
      <span className="block size-full rounded-full bg-white p-[2px]">{inner}</span>
    </span>
  );
}

function AdImage({ src, className }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  return src && !failed ? (
    <img src={src} alt="" className={cx("block w-full object-cover", className)} onError={() => setFailed(true)} />
  ) : (
    <div className={cx("grid w-full place-items-center bg-gradient-to-br from-indigo-200 via-sky-100 to-cyan-100 text-[11px] font-medium text-slate-500", className)}>
      Your ad image
    </div>
  );
}

/** Caption that cuts off with the app's own "… more" / "See more", like the real feed. */
function Clamp({ text, limit, more, className, lead }) {
  const cut = text.length > limit ? text.slice(0, limit).replace(/\s+\S*$/, "") : text;
  return <p className={className}>{lead}{cut}{cut !== text && <span className="text-[#737373]">… {more}</span>}</p>;
}

// ---- Facebook -------------------------------------------------------------------------------------------
function Facebook({ ad }) {
  return (
    <div className="flex min-h-full flex-col bg-[#c9ccd1]/40 text-[#050505]">
      <div className="sticky top-0 z-10 bg-white"><div className="flex items-center justify-between px-3 pb-1.5 pt-1">
        <span className="text-[25px] font-bold tracking-[-0.04em] text-[#0866ff]" style={{ fontFamily: "Helvetica, Arial, sans-serif" }}>facebook</span>
        <span className="flex gap-2">
          {["M12 5v14M5 12h14", "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm9 16-4-4"].map((d) => (
            <span key={d} className="grid size-8 place-items-center rounded-full bg-[#e4e6eb]"><I d={d} size={17} sw={2.6} /></span>
          ))}
          <span className="grid size-8 place-items-center rounded-full bg-[#e4e6eb]">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M12 2C6.4 2 2 6.1 2 11.6c0 2.9 1.2 5.4 3.1 7.1v3.3l3-1.7c1.2.3 2.5.5 3.9.5 5.6 0 10-4.1 10-9.6S17.6 2 12 2Zm1 12.9-2.5-2.7-5 2.7 5.5-5.8 2.6 2.7 4.9-2.7-5.5 5.8Z" /></svg>
          </span>
        </span>
      </div>
      <div className="flex justify-around border-b border-[#ced0d4] bg-white pb-0.5 text-[#65676b]">
        {[["M3 11 12 3l9 8v10h-6v-6H9v6H3Z", true], ["M4 6h16v12H4zM10 9l5 3-5 3Z"], ["M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8 0a3 3 0 1 0 0-6M2 20c0-3 3-5 6-5s6 2 6 5m2-5c3 0 6 2 6 5"],
          ["M4 9h16l-1-5H5ZM5 9v11h14V9M9 20v-6h6v6"], ["M6 16V11a6 6 0 1 1 12 0v5l2 2H4ZM10 21h4"]].map(([d, on], i) => (
          <span key={i} className={cx("flex flex-1 justify-center border-b-[3px] py-1.5", on ? "border-[#0866ff] text-[#0866ff]" : "border-transparent")}><I d={d} size={20} sw={1.9} /></span>
        ))}
      </div></div>
      <div className="mt-2 bg-white">
        <div className="flex items-start gap-2 px-3 pt-3">
          <Avatar brand={ad.brand} logo={ad.logo} size={38} />
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-[14px] font-semibold">{ad.brand}</p>
            <p className="mt-0.5 flex items-center gap-1 text-[12px] text-[#65676b]">Sponsored · <Globe /></p>
          </div>
          <Dots className="text-[#65676b]" />
          <I d="M6 6l12 12M18 6 6 18" size={20} className="text-[#65676b]" />
        </div>
        <Clamp text={ad.text} limit={120} more="See more" className="px-3 pb-2.5 pt-2 text-[14px] leading-[1.34]" />
        <AdImage src={ad.image} className="aspect-square" />
        <div className="flex items-center gap-3 bg-[#f0f2f5] px-3 py-2.5">
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-[11.5px] uppercase text-[#65676b]">{ad.domain}</p>
            <p className="mt-0.5 line-clamp-2 text-[14.5px] font-semibold">{ad.headline}</p>
          </div>
          <span className="shrink-0 rounded-md bg-[#e2e5e9] px-3 py-2 text-[13px] font-semibold">{ad.cta}</span>
        </div>
        <div className="flex items-center justify-between px-3 py-2 text-[12.5px] text-[#65676b]">
          <span className="flex items-center gap-1.5">
            <span className="flex -space-x-1">
              <span className="grid size-[17px] place-items-center rounded-full bg-gradient-to-b from-[#18afff] to-[#0062df] ring-2 ring-white">
                <svg width="9" height="9" viewBox="0 0 16 16" fill="#fff" aria-hidden><path d="M2 7h2v8H2zM5.5 15h6.6a1.5 1.5 0 0 0 1.5-1.3l.9-5A1.5 1.5 0 0 0 13 7H9.6l.5-2.8A1.6 1.6 0 0 0 8.6 2L5.5 7Z" /></svg>
              </span>
              <span className="grid size-[17px] place-items-center rounded-full bg-gradient-to-b from-[#ff6680] to-[#e61739] ring-2 ring-white">
                <svg width="9" height="9" viewBox="0 0 16 16" fill="#fff" aria-hidden><path d="M8 14S1.5 10 1.5 5.6A3.2 3.2 0 0 1 8 4a3.2 3.2 0 0 1 6.5 1.6C14.5 10 8 14 8 14Z" /></svg>
              </span>
            </span>
            {ad.stats.likes}
          </span>
          <span>{ad.stats.comments} comments · {ad.stats.shares} shares</span>
        </div>
        <div className="mx-3 flex justify-around border-t border-[#ced0d4] pb-5 pt-1.5 text-[13px] font-semibold text-[#65676b]">
          {[["Like", "M7 10v11M2 10h5v11H2zM7 10l4-8a2.5 2.5 0 0 1 2.5 3l-.7 4H19a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.8 21H7"],
            ["Comment", "M12 3c5 0 9 3.4 9 7.8s-4 7.7-9 7.7c-1.2 0-2.3-.2-3.4-.5L4 20l1-3.8C3.7 14.8 3 13 3 10.8 3 6.4 7 3 12 3Z"],
            ["Share", "M14 4l7 7-7 7v-4c-6 0-9 2-11 6 1-6 4-10 11-11Z"]].map(([t, d]) => (
            <span key={t} className="flex items-center gap-1.5 py-1"><I d={d} size={17} sw={1.8} />{t}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---- Instagram feed -------------------------------------------------------------------------------------
function Instagram({ ad }) {
  return (
    <div className="flex min-h-full flex-col bg-white text-[#000]">
      <div className="sticky top-0 z-10 flex items-center justify-between bg-white px-3.5 pb-1 pt-0.5">
        <span className="text-[30px] leading-none" style={{ fontFamily: "'Grand Hotel', cursive" }}>Instagram</span>
        <span className="flex items-center gap-4">
          <I d="M12 21s-8-4.9-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 6.1-8 11-8 11Z" size={24} sw={1.9} />
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinejoin="round" aria-hidden>
            <path d="M12 2.8a9.2 9.2 0 0 0-8 13.8L2.8 21.2l4.6-1.2A9.2 9.2 0 1 0 12 2.8Z" /><path d="m7.6 13.8 3-3.2 2.3 2 3.5-3.3-3 3.3-2.3-2Z" strokeLinecap="round" />
          </svg>
        </span>
      </div>
      <div className="flex items-center gap-2.5 px-3 py-2">
        <Avatar brand={ad.brand} logo={ad.logo} size={30} ring />
        <div className="min-w-0 flex-1 leading-tight">
          <p className="truncate text-[13px] font-semibold">{ad.handle}</p>
          <p className="text-[11px] text-[#000]">Sponsored</p>
        </div>
        <Dots />
      </div>
      <AdImage src={ad.image} className="aspect-[4/5] max-h-[300px]" />
      <div className="flex items-center justify-between border-b border-[#efefef] bg-[#0095f6] px-3.5 py-2.5 text-[13.5px] font-semibold text-white">
        {ad.cta}<I d="m9 6 6 6-6 6" size={18} sw={2.2} />
      </div>
      <div className="flex items-center gap-3.5 px-3 pt-2.5">
        <I d="M12 21s-8-4.9-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 6.1-8 11-8 11Z" size={24} sw={1.9} />
        <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinejoin="round" aria-hidden>
          <path d="M20.7 16.8A9.3 9.3 0 1 0 17.3 20.4L21.5 21.5Z" />
        </svg>
        <I d="M22 3 9.2 10.1M22 3l-7 18-5.8-10.9L2 6.7Z" size={22} sw={1.9} />
        <span className="ml-auto"><I d="M19 21 12 16l-7 5V3h14Z" size={23} sw={1.9} /></span>
      </div>
      <p className="px-3 pt-2 text-[13px] font-semibold">{ad.stats.likes} likes</p>
      <Clamp text={ad.text} limit={70} more="more" lead={<b className="font-semibold">{ad.handle} </b>} className="px-3 pt-0.5 text-[13px] leading-[1.35]" />
      <p className="px-3 pt-1 text-[13px] text-[#737373]">View all {ad.stats.comments} comments</p>
      <div className="sticky bottom-0 z-10 mt-auto flex justify-around border-t border-[#dbdbdb] bg-white pb-4 pt-2.5">
        <I d="M3 10.5 12 3l9 7.5V21h-6v-6.5H9V21H3Z" size={24} fill="currentColor" />
        <I d="M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm10 17-5-5" size={24} />
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" aria-hidden>
          <rect x="3" y="3" width="18" height="18" rx="5" /><path d="M3 8.5h18M9 3l3 5.5M14.5 3l3 5.5" /><path d="m10 12 5 3-5 3Z" fill="currentColor" stroke="none" />
        </svg>
        <I d="M4 7h16l-1.5 13h-13ZM9 7V6a3 3 0 0 1 6 0v1" size={24} />
        <Avatar brand={ad.brand} logo={ad.logo} size={24} />
      </div>
    </div>
  );
}

// ---- Instagram Story ------------------------------------------------------------------------------------
function Story({ ad }) {
  return (
    <div className="relative h-[540px] w-full overflow-hidden rounded-t-[10px] bg-black text-white">
      <AdImage src={ad.image} className="absolute inset-0 h-full" />
      <div className="absolute inset-0 bg-gradient-to-b from-black/45 via-transparent via-40% to-black/75" />
      <div className="absolute inset-x-2 top-2 flex gap-[3px]">
        <div className="h-[2px] flex-1 overflow-hidden rounded bg-white/35"><div className="h-full w-full origin-left animate-[storybar_4.2s_linear] bg-white" /></div>
        <div className="h-[2px] flex-1 rounded bg-white/35" />
        <div className="h-[2px] flex-1 rounded bg-white/35" />
      </div>
      <div className="absolute inset-x-3 top-5 flex items-center gap-2">
        <Avatar brand={ad.brand} logo={ad.logo} size={30} />
        <div className="min-w-0 flex-1 leading-tight drop-shadow">
          <p className="truncate text-[13px] font-semibold">{ad.handle}</p>
          <p className="text-[11px] text-white/85">Sponsored</p>
        </div>
        <Dots />
        <I d="M6 6l12 12M18 6 6 18" size={24} />
      </div>
      <div className="absolute inset-x-5 bottom-[150px]">
        <p className="text-[21px] font-bold leading-[1.15] drop-shadow-[0_1px_6px_rgba(0,0,0,.45)]">{ad.headline}</p>
      </div>
      <div className="absolute inset-x-0 bottom-[68px] flex flex-col items-center gap-1.5">
        <I d="m6 15 6-6 6 6" size={22} sw={2.4} className="animate-bounce" />
        <span className="flex items-center gap-1.5 rounded-full bg-white px-4 py-2 text-[13.5px] font-semibold text-[#000] shadow-lg">
          <I d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" size={15} sw={2.4} className="text-[#0095f6]" />
          {ad.cta}
        </span>
      </div>
      <div className="absolute inset-x-3 bottom-5 flex items-center gap-3">
        <span className="flex-1 rounded-full border border-white/60 px-4 py-2 text-[13px] text-white/85">Send message</span>
        <I d="M12 21s-8-4.9-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 6.1-8 11-8 11Z" size={25} sw={1.9} />
        <I d="M22 3 9.2 10.1M22 3l-7 18-5.8-10.9L2 6.7Z" size={24} sw={1.9} />
      </div>
    </div>
  );
}

// ---- Google Search (mobile) -----------------------------------------------------------------------------
function GoogleSearch({ ad }) {
  const g = ["#4285f4", "#ea4335", "#fbbc05", "#4285f4", "#34a853", "#ea4335"];
  return (
    <div className="flex min-h-full flex-col bg-white text-[#202124]" style={{ fontFamily: "Arial, Roboto, sans-serif" }}>
      <div className="sticky top-0 z-10 bg-white"><div className="flex items-center justify-between px-3 pt-1">
        <I d="M4 7h16M4 12h16M4 17h16" size={22} className="text-[#5f6368]" />
        <span className="text-[25px] font-medium tracking-[-0.03em]" style={{ fontFamily: "'Product Sans', Arial, sans-serif" }}>
          {"Google".split("").map((ch, i) => <span key={i} style={{ color: g[i] }}>{ch}</span>)}
        </span>
        <span className="grid size-7 place-items-center rounded-full bg-[#7b1fa2] text-[12px] font-semibold text-white">A</span>
      </div>
      <div className="mx-3 mt-2.5 flex items-center gap-2.5 rounded-full px-4 py-2.5 shadow-[0_1px_6px_rgba(32,33,36,.28)]">
        <I d="M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm10 17-5-5" size={17} className="text-[#9aa0a6]" />
        <span className="min-w-0 flex-1 truncate text-[14px]">{ad.query}</span>
        <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden><path fill="#4285f4" d="M12 15a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v7a3 3 0 0 0 3 3Z" /><path fill="#34a853" d="M17 12a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.9V22h2v-3.1a7 7 0 0 0 6-6.9Z" /></svg>
      </div>
      <div className="mt-2 flex gap-5 border-b border-[#ebebeb] px-4 text-[13px] text-[#5f6368]">
        {["All", "Images", "Maps", "News", "Videos"].map((t, i) => (
          <span key={t} className={cx("pb-2 pt-1.5", i === 0 && "border-b-[3px] border-[#1a73e8] font-medium text-[#1a73e8]")}>{t}</span>
        ))}
      </div></div>
      <div className="px-4 pt-3.5">
        <p className="text-[13px] font-bold">Sponsored</p>
        <div className="mt-2 flex items-center gap-2.5">
          <span className="grid size-[26px] place-items-center rounded-full border border-[#dadce0] bg-[#f1f3f4]"><Avatar brand={ad.brand} logo={ad.logo} size={18} /></span>
          <div className="min-w-0 leading-tight">
            <p className="truncate text-[13.5px]">{ad.brand}</p>
            <p className="truncate text-[11.5px] text-[#4d5156]">https://{ad.domain}</p>
          </div>
          <Dots className="ml-auto shrink-0 rotate-90 text-[#5f6368]" />
        </div>
        <p className="mt-2 text-[17.5px] leading-[1.3] text-[#1a0dab]">{ad.headline} | {ad.brand}</p>
        <p className="mt-1 line-clamp-3 text-[13.5px] leading-[1.45] text-[#4d5156]">{ad.text}</p>
        <div className="mt-2.5 divide-y divide-[#ebebeb] border-t border-[#ebebeb] text-[14px] text-[#1a0dab]">
          {[ad.cta, "Pricing", "Contact us"].map((t) => <p key={t} className="flex justify-between py-2.5">{t}<I d="m9 6 6 6-6 6" size={16} className="text-[#70757a]" /></p>)}
        </div>
      </div>
      <div className="mt-2 border-t-8 border-[#f1f3f4] px-4 pt-3 opacity-60" aria-hidden>
        <div className="flex items-center gap-2.5"><span className="size-[26px] rounded-full bg-[#f1f3f4]" /><span className="h-2.5 w-28 rounded bg-[#e8eaed]" /></div>
        <div className="mt-2.5 h-3.5 w-52 rounded bg-[#d2e3fc]" />
        <div className="mt-2 h-2.5 w-full rounded bg-[#f1f3f4]" /><div className="mt-1.5 h-2.5 w-3/4 rounded bg-[#f1f3f4]" />
      </div>
    </div>
  );
}

// ---- LinkedIn -------------------------------------------------------------------------------------------
function LinkedIn({ ad }) {
  return (
    <div className="flex min-h-full flex-col bg-[#f4f2ee] text-[rgba(0,0,0,.9)]">
      <div className="sticky top-0 z-10 flex items-center gap-2.5 bg-white px-3 py-2">
        <Avatar brand="Y" size={28} />
        <span className="flex flex-1 items-center gap-2 rounded bg-[#edf3f8] px-2.5 py-1.5 text-[13px] text-[rgba(0,0,0,.6)]">
          <I d="M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm10 17-5-5" size={15} sw={2.4} /> Search
        </span>
        <I d="M4 5h16v11H8l-4 4Z" size={22} sw={1.9} className="text-[rgba(0,0,0,.6)]" />
      </div>
      <div className="mt-1.5 bg-white">
        <div className="flex items-start gap-2 px-3 pt-3">
          <Avatar brand={ad.brand} logo={ad.logo} size={44} square />
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-[14px] font-semibold">{ad.brand}</p>
            <p className="mt-0.5 text-[12px] text-[rgba(0,0,0,.6)]">{ad.stats.followers} followers</p>
            <p className="text-[12px] text-[rgba(0,0,0,.6)]">Promoted</p>
          </div>
          <span className="flex items-center gap-1 text-[14px] font-semibold text-[#0a66c2]"><I d="M12 5v14M5 12h14" size={16} sw={2.6} />Follow</span>
        </div>
        <Clamp text={ad.text} limit={110} more="more" className="px-3 pb-2.5 pt-2 text-[14px] leading-[1.42]" />
        <AdImage src={ad.image} className="aspect-[1.91/1]" />
        <div className="flex items-center gap-3 bg-[#eef3f8] px-3 py-2.5">
          <div className="min-w-0 flex-1 leading-tight">
            <p className="line-clamp-2 text-[14px] font-semibold">{ad.headline}</p>
            <p className="mt-0.5 truncate text-[12px] text-[rgba(0,0,0,.6)]">{ad.domain}</p>
          </div>
          <span className="shrink-0 rounded-full border border-[#0a66c2] px-3.5 py-1 text-[14px] font-semibold text-[#0a66c2]">{ad.cta}</span>
        </div>
        <div className="flex items-center justify-between px-3 py-2 text-[12px] text-[rgba(0,0,0,.6)]">
          <span className="flex items-center gap-1">
            <span className="flex -space-x-1">
              <span className="grid size-4 place-items-center rounded-full bg-[#378fe9] ring-2 ring-white"><svg width="8" height="8" viewBox="0 0 16 16" fill="#fff" aria-hidden><path d="M2 7h2v8H2zM5.5 15h6.6a1.5 1.5 0 0 0 1.5-1.3l.9-5A1.5 1.5 0 0 0 13 7H9.6l.5-2.8A1.6 1.6 0 0 0 8.6 2L5.5 7Z" /></svg></span>
              <span className="grid size-4 place-items-center rounded-full bg-[#6dae4f] ring-2 ring-white"><svg width="8" height="8" viewBox="0 0 16 16" fill="#fff" aria-hidden><path d="M3 9l3 3 7-8" stroke="#fff" strokeWidth="2.4" fill="none" /></svg></span>
              <span className="grid size-4 place-items-center rounded-full bg-[#df704d] ring-2 ring-white"><svg width="8" height="8" viewBox="0 0 16 16" fill="#fff" aria-hidden><path d="M8 14S1.5 10 1.5 5.6A3.2 3.2 0 0 1 8 4a3.2 3.2 0 0 1 6.5 1.6C14.5 10 8 14 8 14Z" /></svg></span>
            </span>
            {ad.stats.likes}
          </span>
          <span>{ad.stats.comments} comments · {ad.stats.shares} reposts</span>
        </div>
        <div className="mx-2 flex justify-around border-t border-[#e8e8e8] py-1.5 text-[12px] font-semibold text-[rgba(0,0,0,.6)]">
          {[["Like", "M7 10v11M2 10h5v11H2zM7 10l4-8a2.5 2.5 0 0 1 2.5 3l-.7 4H19a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.8 21H7"],
            ["Comment", "M4 5h16v11H8l-4 4Z"], ["Repost", "M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3"],
            ["Send", "M22 3 9.2 10.1M22 3l-7 18-5.8-10.9L2 6.7Z"]].map(([t, d]) => (
            <span key={t} className="flex flex-col items-center gap-0.5"><I d={d} size={18} sw={1.8} />{t}</span>
          ))}
        </div>
      </div>
      <div className="sticky bottom-0 z-10 mt-auto flex justify-around border-t border-[#e8e8e8] bg-white pb-4 pt-1.5 text-[10px] text-[rgba(0,0,0,.6)]">
        {[["Home", "M3 11 12 3l9 8v10h-6v-6H9v6H3Z", true], ["My Network", "M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8 0a3 3 0 1 0 0-6M2 20c0-3 3-5 6-5s6 2 6 5m2-5c3 0 6 2 6 5"],
          ["Post", "M4 4h16v16H4zM12 8v8M8 12h8"], ["Notifications", "M6 16V11a6 6 0 1 1 12 0v5l2 2H4ZM10 21h4"], ["Jobs", "M3 7h18v13H3zM8 7V4h8v3"]].map(([t, d, on]) => (
          <span key={t} className={cx("flex flex-col items-center gap-0.5", on && "text-[rgba(0,0,0,.9)]")}>
            <I d={d} size={20} sw={on ? 2.2 : 1.8} />{t}
          </span>
        ))}
      </div>
    </div>
  );
}

const RENDER = { facebook: Facebook, instagram: Instagram, story: Story, google: GoogleSearch, linkedin: LinkedIn };

/** Believable engagement numbers that stay the same for a brand (so the preview doesn't flicker). */
function engagement(seed) {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const n = (min, max) => min + (h = (h * 1103515245 + 12345) >>> 0) % (max - min);
  const k = (v) => (v >= 1000 ? `${(v / 1000).toFixed(1).replace(/\.0$/, "")}K` : String(v));
  return { likes: k(n(180, 2400)), comments: n(12, 140), shares: n(4, 60), followers: k(n(1200, 48000)) };
}

function StatusBar({ dark }) {
  return (
    <div className={cx("flex items-center justify-between px-6 pb-1 pt-2.5 text-[12px] font-semibold", dark ? "bg-black text-white" : "bg-white text-black")} style={SYSTEM_FONT} aria-hidden>
      <span>9:41</span>
      <span className="h-[18px] w-[72px] rounded-full bg-black" />
      <span className="flex items-center gap-1">
        <svg width="16" height="10" viewBox="0 0 17 11" fill="currentColor"><rect x="0" y="7" width="3" height="4" rx="1" /><rect x="4.5" y="5" width="3" height="6" rx="1" /><rect x="9" y="2.5" width="3" height="8.5" rx="1" /><rect x="13.5" y="0" width="3" height="11" rx="1" /></svg>
        <svg width="15" height="11" viewBox="0 0 16 12" fill="currentColor"><path d="M8 2.4c2.3 0 4.4.9 6 2.4l1.2-1.2A10.2 10.2 0 0 0 8 .7 10.2 10.2 0 0 0 .8 3.6L2 4.8a8.5 8.5 0 0 1 6-2.4Zm0 3.4c1.4 0 2.6.5 3.6 1.4l1.2-1.2A6.8 6.8 0 0 0 8 4.1C6.2 4.1 4.5 4.8 3.2 6l1.2 1.2c1-.9 2.2-1.4 3.6-1.4Zm0 3.4c-.5 0-1 .2-1.3.5L8 11l1.3-1.3c-.3-.3-.8-.5-1.3-.5Z" /></svg>
        <svg width="25" height="12" viewBox="0 0 26 12" fill="none" stroke="currentColor"><rect x=".5" y=".5" width="22" height="11" rx="3.5" opacity=".4" /><rect x="2" y="2" width="17" height="8" rx="2" fill="currentColor" stroke="none" /><path d="M24 4v4" strokeWidth="1.5" opacity=".5" /></svg>
      </span>
    </div>
  );
}

/**
 * @param creative {headline, text, image_url, cta}
 * @param connected Set of connected provider keys ("meta" | "google" | "linkedin")
 * @param platform  the campaign's own platform; its placements are shown even before connecting
 * @param logo      the brand's logo (Brand Kit), used as the profile picture
 */
export default function AdPlacements({ creative = {}, brand, domain, logo, connected, platform, still }) {
  // `still`: inside the app nothing moves on its own (design.md v3 9); the marketing pages keep the motion.
  const prefersStill = useMemo(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches, []);
  const reduceMotion = prefersStill || !!still;
  const available = PLACEMENTS.filter((p) => connected.has(p.provider) || p.provider === platform);
  const missing = Object.keys(PROVIDER_LABEL).filter((k) => !connected.has(k));
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(reduceMotion);
  const [hover, setHover] = useState(false);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const frame = useRef(null);
  const screen = useRef(null);
  const current = available[Math.min(index, available.length - 1)] || PLACEMENTS[0];

  useEffect(() => { setIndex(0); }, [platform, available.length]);
  useEffect(() => {
    if (paused || hover || available.length < 2) return;
    const t = setTimeout(() => setIndex((i) => (i + 1) % available.length), DWELL_MS);
    return () => clearTimeout(t);
  }, [index, paused, hover, available.length]);

  useEffect(() => {  // after a beat, scroll the feed like a person would, so the headline and button come into view
    const el = screen.current;
    if (!el) return;
    el.scrollTop = 0;
    if (reduceMotion || current.dark || current.still) return;
    const t = setTimeout(() => el.scrollTo({ top: el.scrollHeight - el.clientHeight, behavior: "smooth" }), 1500);
    return () => clearTimeout(t);
  }, [current.key, current.dark, current.still, reduceMotion]);

  const handle = (brand || "yourbrand").toLowerCase().replace(/[^a-z0-9]+/g, "");
  const ad = {
    brand: brand || "Your brand",
    logo,
    handle: handle || "yourbrand",
    domain: domain || `${handle || "yourbrand"}.com`,
    headline: creative.headline || "Your headline goes here",
    text: creative.text || "Your primary text appears here. Use the AI copy button to write it in seconds.",
    image: creative.image_url,
    cta: creative.cta || "Learn more",
    query: `${(creative.headline || brand || "best offers").toLowerCase().slice(0, 40)} near me`,
    stats: engagement(brand || "aimva"),
  };
  const Render = RENDER[current.key];

  const onMove = (e) => {
    if (reduceMotion) return;
    const r = frame.current.getBoundingClientRect();
    setTilt({ x: ((e.clientY - r.top) / r.height - 0.5) * -6, y: ((e.clientX - r.left) / r.width - 0.5) * 8 });
  };

  return (
    <div className="flex flex-col items-center">
      <div className="mb-3 flex w-full items-center justify-between gap-2">
        <p className="text-sm font-semibold text-strong">{current.label}</p>
        {available.length > 1 && (
          <button className="btn-subtle btn-sm" onClick={() => setPaused((p) => !p)} aria-label={paused ? "Play previews" : "Pause previews"}>
            {paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}
          </button>
        )}
      </div>

      <div className="w-full [perspective:1200px]">
        <div
          ref={frame}
          onMouseMove={onMove}
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => { setHover(false); setTilt({ x: 0, y: 0 }); }}
          className="mx-auto w-full max-w-[300px] rounded-[2.6rem] bg-[#1b1b1f] p-[9px] shadow-[0_30px_60px_-20px_rgba(0,0,0,0.55),inset_0_0_0_1.5px_#3a3a40] transition-transform duration-200 ease-out"
          style={{ transform: `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)` }}
        >
          <div className={cx("relative overflow-hidden rounded-[2.1rem]", current.dark ? "bg-black" : "bg-white")} style={SYSTEM_FONT}>
            <StatusBar dark={current.dark} />
            <div ref={screen} className={cx("relative h-[540px] overscroll-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden", current.dark ? "overflow-hidden" : "overflow-y-auto")} style={{ scrollbarWidth: "none" }}>
              <div key={current.key} className={cx("flex min-h-full flex-col [&>*]:flex-1", !reduceMotion && "animate-[adin_450ms_cubic-bezier(.2,.8,.2,1)]")}>
                <Render ad={ad} />
              </div>
            </div>
            <div className="pointer-events-none absolute inset-x-0 bottom-1.5 z-20 flex justify-center" aria-hidden>
              <span className={cx("h-[4px] w-[110px] rounded-full", current.dark ? "bg-white/80" : "bg-black/85")} />
            </div>
          </div>
        </div>
      </div>

      {available.length > 1 && (
        <div className="mt-4 flex w-full max-w-[300px] gap-1.5" role="tablist" aria-label="Ad placements">
          {available.map((p, i) => (
            <button
              key={p.key}
              role="tab"
              aria-selected={i === index}
              aria-label={p.label}
              title={p.label}
              onClick={() => setIndex(i)}
              className="group h-6 flex-1 cursor-pointer"
            >
              <span className="block h-1 overflow-hidden rounded-full bg-ink/10 group-hover:bg-ink/20">
                <span
                  key={i === index ? `${index}-${paused || hover}` : "idle"}
                  className={cx("block h-full origin-left rounded-full bg-brand-2",
                    i < index ? "w-full" : i === index ? (paused || hover || reduceMotion ? "w-full" : "animate-[storybar_4.2s_linear] w-full") : "w-0")}
                />
              </span>
            </button>
          ))}
        </div>
      )}

      {missing.length > 0 && (
        <div className="mt-3 flex flex-wrap justify-center gap-1.5">
          {missing.map((k) => (
            <Link key={k} to="/app/settings?tab=integrations" className="chip border-line text-faint hover:border-line-strong hover:text-ink">
              <Lock className="size-3" /> Connect {PROVIDER_LABEL[k]} to preview there
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
