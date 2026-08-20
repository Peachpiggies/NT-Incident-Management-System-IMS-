import { defineRouting } from "next-intl/routing";
import { locales, defaultLocale } from "./config";

export const routing = defineRouting({
  locales,
  defaultLocale,
  // "as-needed": default locale (en) has no URL prefix (e.g. /dashboard),
  // other locales are prefixed (e.g. /th/dashboard). Matches how most
  // users will bookmark/share links without thinking about locale.
  localePrefix: "as-needed",
});
