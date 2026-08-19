"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { createTicket } from "@/lib/api/tickets";
import { listCategories, listPriorities, listSubcategories } from "@/lib/api/references";
import { apiErrorMessage } from "@/lib/api/client";
import type { CategoryResponse, PriorityResponse, SubcategoryResponse } from "@/lib/types";
import { PageHeader } from "@/components/ui/PageHeader";

export default function NewTicketPage() {
  const t = useTranslations("newTicket");
  const router = useRouter();
  const [categories, setCategories] = useState<CategoryResponse[]>([]);
  const [subcategories, setSubcategories] = useState<SubcategoryResponse[]>([]);
  const [priorities, setPriorities] = useState<PriorityResponse[]>([]);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [subcategoryId, setSubcategoryId] = useState("");
  const [priorityId, setPriorityId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void listCategories().then(setCategories).catch(() => setCategories([]));
    void listPriorities().then(setPriorities).catch(() => setPriorities([]));
  }, []);

  useEffect(() => {
    setSubcategoryId("");
    if (!categoryId) {
      setSubcategories([]);
      return;
    }
    void listSubcategories(categoryId).then(setSubcategories).catch(() => setSubcategories([]));
  }, [categoryId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const ticket = await createTicket({
        title,
        description,
        category_id: categoryId,
        subcategory_id: subcategoryId || null,
        priority_id: priorityId,
        source: "WEB",
      });
      router.push(`/tickets/${ticket.id}`);
    } catch (err) {
      setError(apiErrorMessage(err, t("errorFallback")));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <PageHeader title={t("title")} description={t("description")} />

      <form onSubmit={handleSubmit} className="space-y-5 rounded-card border border-ink-100 bg-white p-6">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-ink-500">{t("titleLabel")}</span>
          <input
            required
            minLength={5}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="rounded-md border border-ink-100 px-3 py-2 text-sm outline-none focus:border-accent-500"
            placeholder={t("titlePlaceholder")}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-ink-500">{t("descriptionLabel")}</span>
          <textarea
            required
            minLength={10}
            rows={5}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="rounded-md border border-ink-100 px-3 py-2 text-sm outline-none focus:border-accent-500"
            placeholder={t("descriptionPlaceholder")}
          />
        </label>

        <div className="grid grid-cols-2 gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-ink-500">{t("category")}</span>
            <select
              required
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              className="rounded-md border border-ink-100 px-3 py-2 text-sm outline-none focus:border-accent-500"
            >
              <option value="">{t("select")}</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-ink-500">{t("subcategory")}</span>
            <select
              value={subcategoryId}
              onChange={(e) => setSubcategoryId(e.target.value)}
              disabled={!categoryId}
              className="rounded-md border border-ink-100 px-3 py-2 text-sm outline-none focus:border-accent-500 disabled:bg-ink-50"
            >
              <option value="">{t("none")}</option>
              {subcategories.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-ink-500">{t("priority")}</span>
          <select
            required
            value={priorityId}
            onChange={(e) => setPriorityId(e.target.value)}
            className="rounded-md border border-ink-100 px-3 py-2 text-sm outline-none focus:border-accent-500"
          >
            <option value="">{t("select")}</option>
            {priorities.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        {error && <p className="text-sm font-medium text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-500 disabled:opacity-60"
        >
          {submitting ? t("creating") : t("createButton")}
        </button>
      </form>
    </div>
  );
}
