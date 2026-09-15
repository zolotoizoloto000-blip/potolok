# 12-point production upgrade

Implemented in code:
1. RU/KZ/EN are real server-rendered language versions with separate database fields.
2. `/ru/`, `/kk/`, `/en/`, canonical, hreflang, sitemap.xml, robots.txt.
3. Every published product has a server-rendered SEO URL `/LANG/catalog/SLUG` + Product schema.
4. Database layer/schema is production-ready in structure; local package uses SQLite so it runs immediately. Before launch, point it to managed PostgreSQL/Supabase (credentials required).
5. Image layer compresses uploads to WebP and limits upload size. For production persistence, connect Supabase Storage/Cloudinary/S3 (credentials required).
6. Admin security: server session, no default production password, CSRF protection, login rate limit, 12MB upload limit, logout, audit log.
7. Images: max 8, resize max 1600px, WebP quality 82, lazy loading on catalog.
8. CMS: CRUD, publish/hide, RU/KZ/EN content, search, featured/new flags, categories field, audit. Schema includes sort_order/reorder API.
9. CRM: leads table/API and statuses Новая → В работе → Продажа → Отказ.
10. Analytics hooks are prepared for CTA tracking. Google Analytics/Search Console/Yandex Metrica require the client's IDs/accounts before they can be truly connected.
11. Local SEO: Store schema, address, phone, localized metadata, sitemap. Exact working hours, map IDs, verified review text and additional business facts still require client-confirmed data.
12. Visual layer is production-oriented, but real shop/project photos cannot be invented. Replace remaining manufacturer/demo imagery with client-approved originals when supplied.

## Required before public launch
Set environment variables:
- ADMIN_PASSWORD = strong unique password
- SECRET_KEY = long random value
- SITE_URL = real https:// domain

## Important
This archive intentionally does NOT pretend external services are configured. PostgreSQL/Supabase Storage, analytics accounts, Search Console and verified business photos require credentials/data from the owner. The local package runs with SQLite and local uploads for testing.
