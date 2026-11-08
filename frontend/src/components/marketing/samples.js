// Sample pages made with AIMVA's own page builder (public/samples). The businesses and people are examples.
// To refresh the screenshots after the builder changes, rebuild them from the same briefs (see docs/LANDING.md).
// tall: height / width of the full-page screenshot ({key}-full.webp), so the phone can scroll it to the end.
export const SAMPLES = [
  {
    key: "homes", tall: 6.667, kind: "Real estate", business: "Skyline Homes", layout: "Showcase layout", place: "Whitefield, Bengaluru",
    lead: { name: "Arjun M.", initial: "A", note: "Wants a site visit on Saturday", score: 86, tint: "#0b6b67" },
  },
  {
    key: "dental", tall: 5.488, kind: "Dental clinic", business: "Smile Studio Dental", layout: "Split layout", place: "Jubilee Hills, Hyderabad",
    lead: { name: "Lakshmi R.", initial: "L", note: "Asked about the free check-up", score: 78, tint: "#a35700" },
  },
  {
    key: "coaching", tall: 5.267, kind: "Coaching institute", business: "Vidya Coaching Centre", layout: "Bento layout", place: "Vijayawada",
    lead: { name: "Kiran T.", initial: "K", note: "Demo class for class 11, evenings", score: 81, tint: "#134e5e" },
  },
  {
    key: "cafe", tall: 4.327, kind: "Tiffin centre", business: "Annapurna Tiffins", layout: "Centered layout", place: "Indiranagar, Bengaluru",
    lead: { name: "Fatima S.", initial: "F", note: "Two ghee dosas for pickup", score: 72, tint: "#7c2d12" },
  },
];

export const sampleImg = (key, size) => `/samples/${key}-${size}.webp`;
export const sampleUrl = (key) => `/samples/${key}.html`;
