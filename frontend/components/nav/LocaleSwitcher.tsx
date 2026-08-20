"use client";

import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { locales, localeLabels, type Locale } from "@/i18n/config";

export function LocaleSwitcher() {
  const t = useTranslations("localeSwitcher");
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  function handleChange(next: Locale) {
    router.replace(pathname, { locale: next });
  }

  return (
    <label className="flex items-center gap-2 text-xs text-ink-300">
      <span className="sr-only">{t("label")}</span>
      <select
        value={locale}
        onChange={(e) => handleChange(e.target.value as Locale)}
        className="rounded-md border border-ink-700 bg-ink-950 px-2 py-1 text-xs text-ink-200 outline-none focus:border-accent-500"
      >
        {locales.map((code) => (
          <option key={code} value={code}>
            {localeLabels[code]}
          </option>
        ))}
      </select>
    </label>
  );
}
