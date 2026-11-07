// Who AIMVA is for. The examples quote the real industry templates (backend/app/routers/onboarding.py TEMPLATES),
// so what a visitor reads here is what their first page and call script actually start with.
// `signup` is appended to /signup so onboarding starts pre-filled (see lib/signupHint.js).

export const USE_CASES = [
  {
    slug: "local-businesses",
    short: "Local businesses",
    title: "For clinics, builders, coaches and restaurants",
    lede: "You're good at the work. Answering every enquiry at 9 pm, and remembering who to call back, is the part that slips.",
    problem: [
      "Enquiries arrive on Instagram, WhatsApp, the website and the phone, and live in four places.",
      "The people who ask at night or on a busy day wait until tomorrow, and by then they've booked elsewhere.",
      "You boost a post or run an ad, but can't tell which one actually brought customers.",
    ],
    how: [
      ["A page that's already written", "Pick your kind of business and AIMVA writes the page, the offer and the form. Publish it on AIMVA, your own domain, Netlify or Vercel."],
      ["Every enquiry in one list", "Page forms, WhatsApp chats and calls land in Leads by themselves (Meta lead forms when you sync), scored so the serious ones are on top."],
      ["A reply in seconds", "Connect your WhatsApp and Twilio numbers: Lead Concierge says hello on WhatsApp in seconds and follows up on day 2 and day 7, and the call assistant rings back and asks your questions."],
      ["You see what paid off", "Results shows spend, leads and sales per campaign, and what to fix next."],
    ],
    examples: [
      { name: "Clinics", industry: "healthcare", offer: "Book your first consultation", cta: "Book an appointment", greeting: "Hello! Thanks for contacting our clinic. I can help you book an appointment." },
      { name: "Real estate", industry: "real_estate", offer: "Free site visit this weekend", cta: "Book a site visit", greeting: "Hi! Thanks for your interest in our homes. I'll ask a few quick questions to find the right property for you." },
      { name: "Coaching and classes", industry: "education", offer: "Free demo class", cta: "Book a free demo", greeting: "Hi! Thanks for your interest in our courses. Let me ask a few quick questions." },
      { name: "Restaurants and local services", industry: "services", offer: "Free quote in 24 hours", cta: "Get a free quote", greeting: "Hi! Thanks for calling. I'll take a few details so we can send you a quote." },
    ],
    signup: "&for=own",
  },
  {
    slug: "solo",
    short: "Solo founders and freelancers",
    title: "For founders, consultants and creators working alone",
    lede: "There's one of you. Marketing has to run while you do the actual work.",
    problem: [
      "You don't have time to learn an ad manager, a page builder and a CRM.",
      "A designer for every post and a developer for every page isn't in the budget.",
      "Leads from a talk, a post or a referral end up in your notes app.",
    ],
    how: [
      ["Start from one sentence", "Paste your website or describe what you sell. The Launch agent drafts the page, the ads and the call-back script in one go."],
      ["Pictures and short videos", "Ad pictures from a sentence, free and in your brand's colours. Short promo videos when you add a fal.ai key."],
      ["Your own name, your voice", "Pages and scripts speak as you, not as a company. Practise calls in your browser in English, Hindi, Telugu, Tamil and more; phone calls are in English today."],
      ["Small, clear numbers", "Home tells you in one sentence how the week went; Results shows which ad or page brought the leads."],
    ],
    signup: "&for=personal",
  },
  {
    slug: "agencies",
    short: "Agencies",
    title: "For agencies and freelancers running clients",
    lede: "One login for every client, with their data kept apart, and clients who can see results without asking you for screenshots.",
    problem: [
      "Each client has its own ad accounts, sheets and WhatsApp number, and you switch tabs all day.",
      "Approvals happen in chat threads, and things go live before the client said yes.",
      "Monthly reports take an afternoon to put together by hand.",
    ],
    how: [
      ["A workspace per client", "Each client gets their own pages, campaigns, leads and results. Switch with ⌘K or the client switcher."],
      ["People and roles", "Invite your team as admins or editors, and the client as a viewer who can approve."],
      ["Approvals before anything goes live", "Turn approval on and Publish becomes “Send for approval”. The client approves or asks for changes from their bell."],
      ["Reports in one click", "Leads, Results and Analytics download as clear PDF reports with the numbers that matter and what to do next."],
    ],
    signup: "&for=clients",
  },
];

export const useCase = (slug) => USE_CASES.find((u) => u.slug === slug);
