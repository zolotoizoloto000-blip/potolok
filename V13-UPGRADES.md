# V13 — 12 weaknesses addressed

1. PostgreSQL: DATABASE_URL deployment slot + psycopg dependency added. SQLite remains a zero-config local fallback; live PostgreSQL still needs the real connection string.
2. Persistent images: Supabase Storage configuration adapter/env slots added. Local fallback remains for offline demo; real storage needs Supabase credentials.
3. CTA tracking: server lead endpoint retained; CRM records source. Production analytics IDs can be added at deploy.
4. CRM: lead table, statuses, admin lead screen and audit trail retained.
5. Photo management: existing photos can now be individually removed; new photos append instead of replacing the whole gallery.
6. Product ordering: backend reorder endpoint/sort_order retained as foundation.
7. Categories: category schema retained and frontend category presentation strengthened; full category CRUD can be expanded after client category list is confirmed.
8. Security: CSRF, login throttling, secure session cookie settings, no hardcoded usable production password, logout, audit log, upload limit.
9. SEO: server-rendered RU/KK/EN URLs, localized metadata, hreflang, canonical, sitemap, robots, individual product pages.
10. Product schema: Offer is now emitted only when a real price exists and price-on-request is false.
11. Premium frontend: restored richer commercial sections, ALTOR/LEDMAN proof, solution cards, FAQ and 2GIS CTA while preserving V12 SSR/CMS.
12. Trust: only publicly verified ALTOR/LEDMAN relationship and real address/phone are used; no fake reviews or invented project photos.

Still requires owner/external credentials at launch: actual DATABASE_URL, Supabase keys, analytics/Search Console/Metrica IDs, real approved photos, exact working hours and any client-approved review quotations.
