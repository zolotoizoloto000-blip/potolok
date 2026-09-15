# V14 fixes

- Real DB adapter: uses PostgreSQL when DATABASE_URL is set, SQLite locally.
- Secure cookie configuration retained for HTTPS production.
- Category CRUD in admin and SSR SEO category pages.
- Product ordering controls wired to reorder API.
- Existing photo gallery can remove and reorder photos; first photo is the main image.
- Premium 404 page.
- Product schema no longer emits a fake zero-price Offer.
- CRM, CSRF, login throttling, audit log and multilingual SSR remain.
- SQLite backup helper added.

External-only items remain intentionally un-faked:
- Supabase Storage needs real SUPABASE_URL / SERVICE_KEY / bucket.
- Analytics/Search Console/Metrica need owner account IDs.
- 2FA requires a chosen owner identity/email/auth provider.
- Real business photos, working hours and review quotations need client approval.
