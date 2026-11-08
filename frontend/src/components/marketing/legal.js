// The business details the legal pages need. Fill these in once, here, before launch.
// Until a value is filled in, the pages show it as a highlighted [placeholder] so nothing half-done looks final.
// Set `reviewed: true` only after a lawyer has read Privacy, Terms and Refund: it removes the "draft" banner.
export const LEGAL = {
  reviewed: false,
  effectiveDate: "",          // e.g. "1 December 2026"
  legalName: "",              // the registered entity, e.g. "Example Technologies Private Limited"
  address: "",                // registered office address
  supportEmail: "",           // e.g. support@yourdomain.in
  phone: "",                  // a number customers can call during business hours
  hours: "",                  // e.g. "Monday to Friday, 10 am to 6 pm IST"
  grievanceOfficer: "",       // name of the person who answers privacy complaints (DPDP Act)
  grievanceEmail: "",         // e.g. grievance@yourdomain.in
  courtsCity: "",             // the city whose courts handle disputes, e.g. "Hyderabad"
  serverRegion: "",           // where the servers run, e.g. "India (Mumbai)"
};

export const LEGAL_PAGES = [
  { to: "/privacy", label: "Privacy" },
  { to: "/terms", label: "Terms" },
  { to: "/refund", label: "Refunds" },
  { to: "/contact", label: "Contact" },
];
