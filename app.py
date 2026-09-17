
from flask import Flask, render_template, request, jsonify, session, redirect, abort, url_for, send_from_directory
from pathlib import Path
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass
from io import BytesIO
import sqlite3, json, uuid, os, time, secrets, hashlib, re

BASE=Path(__file__).resolve().parent
DATABASE_URL=os.environ.get("DATABASE_URL","")
UPLOAD=BASE/"static"/"uploads"; UPLOAD.mkdir(parents=True,exist_ok=True)
DB=BASE/"catalog.db"
app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE","1")=="1")
app.config["MAX_CONTENT_LENGTH"]=12*1024*1024
ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD","")
ADMIN_HASH=os.environ.get("ADMIN_PASSWORD_HASH","")
SITE_URL=os.environ.get("SITE_URL","").rstrip("/")
ALLOWED={"jpg","jpeg","png","webp","bmp","tif","tiff","gif","avif","heic","heif"}
LOGIN_ATTEMPTS={}

@app.after_request
def security_headers(response):
    """Safe defaults for both the public site and the admin panel."""
    response.headers.setdefault("X-Content-Type-Options","nosniff")
    response.headers.setdefault("X-Frame-Options","SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy","strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy","camera=(), microphone=(), geolocation=()")
    if request.path.startswith("/admin") or request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control","no-store")
    return response

def db():
    from db_adapter import Conn
    return Conn()

def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS products(
          id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE,
          name_ru TEXT NOT NULL, name_kz TEXT, name_en TEXT,
          description_ru TEXT, description_kz TEXT, description_en TEXT,
          specs_ru TEXT, specs_kz TEXT, specs_en TEXT,
          category TEXT, brand TEXT, price REAL, unit TEXT, old_price REAL,
          stock TEXT, sku TEXT, status TEXT DEFAULT 'Опубликован',
          ask_price INTEGER DEFAULT 0, featured INTEGER DEFAULT 0, new_item INTEGER DEFAULT 0,
          photos TEXT DEFAULT '[]', sort_order INTEGER DEFAULT 0,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS leads(
          id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, source TEXT, name TEXT, phone TEXT,
          message TEXT, status TEXT DEFAULT 'Новая', manager_note TEXT, next_contact TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS categories(
          id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE, title_ru TEXT, title_kz TEXT, title_en TEXT, sort_order INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS audit_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, entity TEXT, entity_id INTEGER, detail TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS site_settings(
          key TEXT PRIMARY KEY, value TEXT DEFAULT '', updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        """)
init()
def migrate():
    with db() as c:
        if os.environ.get("DATABASE_URL",""):
            for n,t in [("manager_note","TEXT"),("next_contact","TEXT"),("updated_at","TIMESTAMP")]:
                try:c.execute(f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {n} {t}")
                except:pass
        else:
            try: existing={r["name"] for r in c.execute("PRAGMA table_info(leads)")}
            except: existing=set()
            for n,t in [("manager_note","TEXT"),("next_contact","TEXT"),("updated_at","TIMESTAMP")]:
                if n not in existing:
                    try:c.execute(f"ALTER TABLE leads ADD COLUMN {n} {t}")
                    except:pass
migrate()

DEFAULT_SETTINGS={
 "hero_eyebrow":"Алматы · Рыскулова 48А/2",
 "hero_title":"Современный потолок под ваш интерьер — в одном месте.",
 "hero_text":"Подберём потолочную систему, профиль и освещение под помещение и бюджет. Отправьте фото комнаты — поможем собрать совместимое решение и уточнить стоимость.",
 "catalog_title":"Системы и комплектующие.",
 "catalog_text":"Актуальную цену и наличие конкретной позиции уточняйте перед заказом.",
 "site_background_image":"",
 "phone":"+7 777 268 72 38", "whatsapp":"77772687238",
 "address":"Алматы, проспект Турара Рыскулова, 48А/2",
 "gis_url":"https://2gis.kz/almaty/firm/70000001061828426", "instagram_url":"",
 "faq1_q":"Можно подобрать систему по фотографии комнаты?",
 "faq1_a":"Да. Отправьте фотографию, примерную площадь и пожелания — специалист поможет определить подходящее решение.",
 "faq2_q":"Есть решения ALTOR и LEDMAN?",
 "faq2_a":"Поможем подобрать профильные системы ALTOR и освещение LEDMAN. Наличие конкретной позиции уточняйте перед заказом.",
 "faq3_q":"Где вы находитесь?", "faq3_a":"Алматы, проспект Турара Рыскулова, 48А/2.",
 "faq4_q":"Как узнать стоимость?", "faq4_a":"Стоимость зависит от выбранной системы, размеров и комплектации. Оставьте заявку или напишите в WhatsApp.",
 "faq5_q":"", "faq5_a":"",
 "faq6_q":"", "faq6_a":"",
 "faq7_q":"", "faq7_a":"",
 "faq8_q":"", "faq8_a":"",
 "faq9_q":"", "faq9_a":"",
 "faq10_q":"", "faq10_a":"",
 "faq11_q":"", "faq11_a":"",
 "faq12_q":"", "faq12_a":"",
 "seo_title_ru":"Центр Потолков — натяжные потолки, ALTOR и LEDMAN в Алматы",
 "seo_description_ru":"Натяжные потолки и потолочные системы в Алматы: профили ALTOR, освещение LEDMAN, комплектующие и подбор решения.",
 "seo_title_kz":"Центр Потолков — Алматыдағы керме төбелер, ALTOR және LEDMAN",
 "seo_description_kz":"Алматыдағы керме төбелер мен төбе жүйелері: ALTOR профильдері, LEDMAN жарықтандыруы, жинақтау және таңдау.",
 "seo_title_en":"Centr Potolkov — stretch ceilings, ALTOR and LEDMAN in Almaty",
 "seo_description_en":"Stretch ceilings and ceiling systems in Almaty: ALTOR profiles, LEDMAN lighting, components and solution selection."
}
def get_settings():
    out=dict(DEFAULT_SETTINGS)
    with db() as c:
        for r in c.execute("SELECT key,value FROM site_settings").fetchall(): out[r["key"]]=r["value"] or ""
    return out

def slugify(s):
    alphabet={"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo","ж":"zh","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"kh","ц":"ts","ч":"ch","ш":"sh","щ":"shch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya","ә":"a","ғ":"g","қ":"q","ң":"n","ө":"o","ұ":"u","ү":"u","һ":"h","і":"i"}
    text="".join(alphabet.get(c,c) for c in s.lower())
    return re.sub(r"[^a-z0-9]+","-",text).strip("-") or uuid.uuid4().hex[:8]

def log(action,entity,eid=None,detail=""):
    with db() as c:c.execute("INSERT INTO audit_log(action,entity,entity_id,detail) VALUES(?,?,?,?)",(action,entity,eid,detail))

def is_admin(): return session.get("admin") is True
def csrf():
    if "csrf" not in session: session["csrf"]=secrets.token_urlsafe(24)
    return session["csrf"]
def require_csrf():
    token=request.headers.get("X-CSRF-Token") or request.form.get("csrf")
    if not token or not secrets.compare_digest(token,session.get("csrf","")): abort(403)

def verify_password(pw):
    if ADMIN_HASH: return check_password_hash(ADMIN_HASH,pw)
    return bool(ADMIN_PASSWORD) and secrets.compare_digest(ADMIN_PASSWORD,pw)

def row_product(r):
    d=dict(r); d["photos"]=json.loads(d.get("photos") or "[]")
    for k in ("ask_price","featured","new_item"): d[k]=bool(d[k])
    return d

def localized(d,lang):
    lang="kz" if lang=="kk" else lang
    return {
      **d,
      "name":d.get(f"name_{lang}") or d.get("name_ru",""),
      "description":d.get(f"description_{lang}") or d.get("description_ru",""),
      "specs":d.get(f"specs_{lang}") or d.get("specs_ru","")
    }


def _store_webp(name,payload):
    supa=os.environ.get("SUPABASE_URL","").rstrip("/")
    key=os.environ.get("SUPABASE_SERVICE_KEY","")
    bucket=os.environ.get("SUPABASE_BUCKET","product-images")
    if supa and key:
        import urllib.request
        req=urllib.request.Request(f"{supa}/storage/v1/object/{bucket}/{name}",data=payload,method="POST",
          headers={"Authorization":f"Bearer {key}","apikey":key,"Content-Type":"image/webp","x-upsert":"false"})
        urllib.request.urlopen(req,timeout=20).read()
        return f"{supa}/storage/v1/object/public/{bucket}/{name}"
    (UPLOAD/name).write_bytes(payload)
    return "/static/uploads/"+name

def delete_image_url(u):
    if u.startswith("/static/uploads/"):
        try:(BASE/u.lstrip("/")).unlink(missing_ok=True)
        except:pass
        return
    supa=os.environ.get("SUPABASE_URL","").rstrip("/"); key=os.environ.get("SUPABASE_SERVICE_KEY","")
    bucket=os.environ.get("SUPABASE_BUCKET","product-images")
    prefix=f"{supa}/storage/v1/object/public/{bucket}/" if supa else ""
    if prefix and u.startswith(prefix) and key:
        import urllib.request
        try:
            req=urllib.request.Request(f"{supa}/storage/v1/object/{bucket}/{u[len(prefix):]}",method="DELETE",
              headers={"Authorization":f"Bearer {key}","apikey":key})
            urllib.request.urlopen(req,timeout=15).read()
        except:pass

def save_one_image(f, prefix="img"):
    if not f or not f.filename: raise ValueError("Выберите изображение")
    try:
        im=Image.open(f.stream)
        try:
            from PIL import ImageOps
            im=ImageOps.exif_transpose(im)
        except: pass
        if getattr(im,"is_animated",False): im.seek(0)
        im.thumbnail((2200,2200))
        if im.mode not in ("RGB","RGBA"): im=im.convert("RGB")
        name=f"{prefix}-{uuid.uuid4().hex}.webp"; buf=BytesIO()
        im.save(buf,"WEBP",quality=84,method=6)
        return _store_webp(name,buf.getvalue())
    except Exception as exc:
        app.logger.exception("Image upload failed")
        raise ValueError("Формат изображения не удалось прочитать. Используйте фото из галереи: JPG, PNG, HEIC/HEIF, WebP, AVIF, TIFF, BMP или GIF.") from exc

def save_images(files):
    urls=[]
    if len([f for f in files if f and f.filename])>8:raise ValueError("Не более 8 фотографий на товар")
    for f in files:
        if not f or not f.filename: continue
        try:
            urls.append(save_one_image(f,"product"))
        except ValueError:
            raise
    return urls

@app.context_processor
def inject(): return {"csrf_token":csrf(),"site_url":SITE_URL}

@app.route("/admin/login", methods=["GET","POST"], strict_slashes=False)
def login():
    ip=request.headers.get("X-Forwarded-For",request.remote_addr or "").split(",")[0].strip()
    now=time.time(); attempts=[t for t in LOGIN_ATTEMPTS.get(ip,[]) if now-t<900]
    LOGIN_ATTEMPTS[ip]=attempts
    if request.method=="POST":
        if len(attempts)>=8:return render_template("login.html",error="Слишком много попыток. Повторите позже."),429
        if verify_password(request.form.get("password","")):
            session.clear();session["admin"]=True;session["csrf"]=secrets.token_urlsafe(24);LOGIN_ATTEMPTS.pop(ip,None)
            log("login","admin",detail=ip);return redirect("/admin")
        attempts.append(now);LOGIN_ATTEMPTS[ip]=attempts
        return render_template("login.html",error="Неверный пароль"),401
    return render_template("login.html",error=None)

@app.route("/admin/logout", methods=["POST"], strict_slashes=False)
def logout(): require_csrf();session.clear();return redirect("/admin/login")

@app.route("/admin", methods=["GET"], strict_slashes=False)
def admin():
    if not is_admin():return redirect("/admin/login")
    return render_template("admin.html")

@app.get("/")
def root(): return redirect("/ru/",302)

@app.get("/<lang>/")
def home(lang):
    if lang not in ("ru","kk","en"):abort(404)
    with db() as c:
        rows=c.execute("SELECT * FROM products WHERE status='Опубликован' ORDER BY featured DESC,sort_order,id DESC").fetchall()
        cats=c.execute("SELECT * FROM categories ORDER BY sort_order,id").fetchall()
    items=[localized(row_product(r),lang) for r in rows]
    ck="title_"+("kz" if lang=="kk" else lang)
    categories=[{**dict(x),"title":x[ck] or x["title_ru"]} for x in cats]
    return render_template("site.html",lang=lang,products=items,categories=categories,settings=get_settings())

@app.get("/<lang>/catalog/<slug>")
def product_page(lang,slug):
    if lang not in ("ru","kk","en"):abort(404)
    with db() as c:r=c.execute("SELECT * FROM products WHERE slug=? AND status='Опубликован'",(slug,)).fetchone()
    if not r:abort(404)
    return render_template("product.html",lang=lang,p=localized(row_product(r),lang))


@app.get("/api/settings")
def api_settings():
    if not is_admin(): return jsonify(error="unauthorized"),401
    return jsonify(get_settings())

@app.put("/api/settings")
def save_settings():
    if not is_admin(): return jsonify(error="unauthorized"),401
    require_csrf()
    data=request.get_json(silent=True) or {}
    allowed=set(DEFAULT_SETTINGS)
    with db() as c:
        for k,v in data.items():
            if k not in allowed: continue
            v=str(v)[:4000]
            c.execute("INSERT INTO site_settings(key,value,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",(k,v))
    log("update","site_settings")
    return jsonify(ok=True,settings=get_settings())


@app.post("/api/site-background")
def site_background_upload():
    if not is_admin(): return jsonify(error="unauthorized"),401
    require_csrf()
    f=request.files.get("background")
    try: url=save_one_image(f,"background")
    except ValueError as exc: return jsonify(error=str(exc)),400
    old=get_settings().get("site_background_image","")
    with db() as c:
        c.execute("INSERT INTO site_settings(key,value,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",("site_background_image",url))
    if old and old!=url: delete_image_url(old)
    log("update","site_background")
    return jsonify(ok=True,url=url,settings=get_settings())

@app.delete("/api/site-background")
def site_background_delete():
    if not is_admin(): return jsonify(error="unauthorized"),401
    require_csrf(); old=get_settings().get("site_background_image","")
    with db() as c:
        c.execute("INSERT INTO site_settings(key,value,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value='',updated_at=CURRENT_TIMESTAMP",("site_background_image",""))
    if old: delete_image_url(old)
    return jsonify(ok=True,settings=get_settings())

@app.get("/api/categories")
def api_categories():
    with db() as c:r=c.execute("SELECT * FROM categories ORDER BY sort_order,id").fetchall()
    return jsonify([dict(x) for x in r])

@app.post("/api/categories")
def add_category():
    if not is_admin():return jsonify(error="unauthorized"),401
    require_csrf()
    data=request.get_json(silent=True) if request.is_json else request.form
    data=data or {}
    ru=str(data.get("title_ru","")).strip()
    if not ru:return jsonify(error="Название обязательно"),400
    sl=slugify(str(data.get("slug","")).strip() or ru)
    with db() as c:
        if c.execute("SELECT 1 FROM categories WHERE slug=?",(sl,)).fetchone():
            return jsonify(error="Категория с таким адресом уже существует"),409
        c.execute("INSERT INTO categories(slug,title_ru,title_kz,title_en,sort_order) VALUES(?,?,?,?,?)",(sl,data.get("title_ru",""),data.get("title_kz",""),data.get("title_en",""),data.get("sort_order",0)))
        r=c.execute("SELECT * FROM categories WHERE slug=?",(sl,)).fetchone()
    log("create","category",r["id"],ru);return jsonify(dict(r)),201

@app.put("/api/categories/<int:cid>")
def update_category(cid):
    if not is_admin():return jsonify(error="unauthorized"),401
    require_csrf()
    data=request.get_json(silent=True) if request.is_json else request.form
    data=data or {}
    ru=str(data.get("title_ru","")).strip()
    if not ru:return jsonify(error="Название обязательно"),400
    with db() as c:
        old=c.execute("SELECT * FROM categories WHERE id=?",(cid,)).fetchone()
        if not old:return jsonify(error="not found"),404
        sl=slugify(str(data.get("slug","")).strip() or ru)
        if c.execute("SELECT 1 FROM categories WHERE slug=? AND id<>?",(sl,cid)).fetchone():
            return jsonify(error="Категория с таким адресом уже существует"),409
        c.execute("UPDATE categories SET slug=?,title_ru=?,title_kz=?,title_en=?,sort_order=? WHERE id=?",(sl,ru,data.get("title_kz",ru),data.get("title_en",ru),data.get("sort_order",old["sort_order"]),cid))
        c.execute("UPDATE products SET category=? WHERE category=?",(ru,old["title_ru"]))
        r=c.execute("SELECT * FROM categories WHERE id=?",(cid,)).fetchone()
    log("update","category",cid,ru);return jsonify(dict(r))

@app.delete("/api/categories/<int:cid>")
def del_category(cid):
    if not is_admin():return jsonify(error="unauthorized"),401
    require_csrf()
    with db() as c:
        old=c.execute("SELECT * FROM categories WHERE id=?",(cid,)).fetchone()
        if old: c.execute("UPDATE products SET category='' WHERE category=?",(old["title_ru"],))
        c.execute("DELETE FROM categories WHERE id=?",(cid,))
    log("delete","category",cid);return jsonify(ok=True)

@app.get("/<lang>/category/<slug>")
def category_page(lang,slug):
    if lang not in ("ru","kk","en"):abort(404)
    with db() as c:
        cat=c.execute("SELECT * FROM categories WHERE slug=?",(slug,)).fetchone()
        if not cat:abort(404)
        title=cat["title_"+("kz" if lang=="kk" else lang)] or cat["title_ru"]
        rows=c.execute("SELECT * FROM products WHERE status='Опубликован' AND category=? ORDER BY featured DESC,sort_order,id DESC",(cat["title_ru"],)).fetchall()
    return render_template("category.html",lang=lang,title=title,slug=slug,products=[localized(row_product(r),lang) for r in rows])

@app.get("/sitemap.xml")
def sitemap():
    with db() as c:
        slugs=[r["slug"] for r in c.execute("SELECT slug FROM products WHERE status='Опубликован'")]
        cats=[r["slug"] for r in c.execute("SELECT slug FROM categories")]
    from xml.sax.saxutils import escape
    urls=[]
    base=SITE_URL or request.url_root.rstrip("/")
    for l in ("ru","kk","en"):
        urls.append(f"{base}/{l}/")
        urls += [f"{base}/{l}/catalog/{x}" for x in slugs]
        urls += [f"{base}/{l}/category/{x}" for x in cats]
    xml='<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f"<url><loc>{escape(u)}</loc></url>" for u in urls)+"</urlset>"
    return app.response_class(xml,mimetype="application/xml")

@app.get("/robots.txt")
def robots(): return app.response_class(f"User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: {SITE_URL or request.url_root.rstrip(chr(47))}/sitemap.xml\n",mimetype="text/plain")

@app.get("/api/products")
def api_products():
    if request.args.get("all")=="1":
        if not is_admin():return jsonify(error="unauthorized"),401
        q="SELECT * FROM products ORDER BY sort_order,id DESC"
    else:q="SELECT * FROM products WHERE status='Опубликован' ORDER BY featured DESC,sort_order,id DESC"
    with db() as c:rows=c.execute(q).fetchall()
    return jsonify([row_product(r) for r in rows])

def product_form(old=None):
    g=lambda k,d="": request.form[k] if k in request.form else ((old or {}).get(k,d))
    def num(k):
        try:return float(g(k)) if str(g(k)).strip() else None
        except:return None
    return dict(
      name_ru=g("name_ru").strip(),name_kz=g("name_kz"),name_en=g("name_en"),
      description_ru=g("description_ru"),description_kz=g("description_kz"),description_en=g("description_en"),
      specs_ru=g("specs_ru"),specs_kz=g("specs_kz"),specs_en=g("specs_en"),
      category=g("category"),brand=g("brand"),price=num("price"),unit=g("unit"),old_price=num("old_price"),
      stock=g("stock","В наличии"),sku=g("sku"),status=g("status","Опубликован"),
      ask_price=1 if g("ask_price","0")=="1" else 0,featured=1 if g("featured","0")=="1" else 0,new_item=1 if g("new_item","0")=="1" else 0)

@app.post("/api/products")
def create_product():
    if not is_admin():return jsonify(error="unauthorized"),401
    require_csrf();d=product_form()
    if not d["name_ru"]:return jsonify(error="Название RU обязательно"),400
    slug=slugify(d["name_ru"]);
    try: photos=save_images(request.files.getlist("photos"))
    except ValueError as exc:return jsonify(error=str(exc)),400
    with db() as c:
        base=slug;n=2
        while c.execute("SELECT 1 FROM products WHERE slug=?",(slug,)).fetchone():slug=f"{base}-{n}";n+=1
        d.update(slug=slug,photos=json.dumps(photos))
        ks=list(d);c.execute(f"INSERT INTO products({','.join(ks)}) VALUES({','.join('?' for _ in ks)})",[d[k] for k in ks])
        r=c.execute("SELECT * FROM products WHERE slug=?",(slug,)).fetchone(); pid=r["id"]
    log("create","product",pid,d["name_ru"]);return jsonify(row_product(r)),201

@app.put("/api/products/<int:pid>")
def update_product(pid):
    if not is_admin():return jsonify(error="unauthorized"),401
    require_csrf()
    with db() as c:
        r=c.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
        if not r:return jsonify(error="not found"),404
        old=row_product(r);d=product_form(old)
        try:new=save_images(request.files.getlist("photos"))
        except ValueError as exc:return jsonify(error=str(exc)),400
        try: kept=json.loads(request.form.get("keep_photos","null"))
        except: kept=None
        if not isinstance(kept,list): kept=old["photos"]
        kept=[u for u in kept if u in old["photos"]]
        removed=[u for u in old["photos"] if u not in kept]
        if len(kept)+len(new)>8:return jsonify(error="Не более 8 фотографий на товар"),400
        d["photos"]=json.dumps(kept+new);d["updated_at"]="CURRENT_TIMESTAMP"
        # timestamp separately to avoid SQL literal as bound string
        d.pop("updated_at")
        c.execute("UPDATE products SET "+",".join(f"{k}=?" for k in d)+",updated_at=CURRENT_TIMESTAMP WHERE id=?",list(d.values())+[pid])
        r=c.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
    for u in removed: delete_image_url(u)
    log("update","product",pid,d["name_ru"]);return jsonify(row_product(r))

@app.delete("/api/products/<int:pid>")
def delete_product(pid):
    if not is_admin():return jsonify(error="unauthorized"),401
    require_csrf()
    with db() as c:
        r=c.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
        if not r:return jsonify(error="not found"),404
        d=row_product(r)
        for u in d["photos"]:
            delete_image_url(u)
        c.execute("DELETE FROM products WHERE id=?",(pid,))
    log("delete","product",pid,d["name_ru"]);return jsonify(ok=True)

@app.post("/api/products/reorder")
def reorder():
    if not is_admin():return jsonify(error="unauthorized"),401
    require_csrf(); ids=request.json.get("ids",[])
    with db() as c:
        for i,pid in enumerate(ids):c.execute("UPDATE products SET sort_order=? WHERE id=?",(i,pid))
    log("reorder","products");return jsonify(ok=True)

@app.post("/api/leads")
def create_lead():
    data=request.get_json(silent=True) or request.form
    name=str(data.get("name", "")).strip()[:120]
    phone=str(data.get("phone", "")).strip()[:40]
    message=str(data.get("message", "")).strip()[:3000]
    source=str(data.get("source", "site")).strip()[:100]
    if not name or len(''.join(x for x in phone if x.isdigit()))<10:
        return jsonify(error="Укажите имя и корректный номер телефона"),400
    if data.get("website"): return jsonify(ok=True),201
    if not hasattr(create_lead,"hits"): create_lead.hits={}
    ip=request.remote_addr or "unknown"; now=time.monotonic()
    hits=[t for t in create_lead.hits.get(ip,[]) if now-t<3600]
    if len(hits)>=12:return jsonify(error="Слишком много заявок. Попробуйте позже."),429
    hits.append(now);create_lead.hits[ip]=hits
    with db() as c:c.execute("INSERT INTO leads(product_id,source,name,phone,message) VALUES(?,?,?,?,?)",(data.get("product_id") or None,source,name,phone,message))
    return jsonify(ok=True),201

@app.get("/api/leads")
def leads():
    if not is_admin():return jsonify(error="unauthorized"),401
    with db() as c:r=c.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()
    return jsonify([dict(x) for x in r])

@app.put("/api/leads/<int:lid>")
def lead_status(lid):
    if not is_admin():return jsonify(error="unauthorized"),401
    require_csrf()
    data=request.get_json(silent=True) if request.is_json else request.form
    data=data or {}
    allowed={"Новая","В работе","Продажа","Отказ","Закрыта","new","work","won","lost"}
    status=str(data.get("status","Новая"))
    if status not in allowed:return jsonify(error="Некорректный статус"),400
    note=str(data.get("manager_note",""))[:3000]
    nxt=str(data.get("next_contact",""))[:40]
    with db() as c:
        existing=c.execute("SELECT id FROM leads WHERE id=?",(lid,)).fetchone()
        if not existing:return jsonify(error="Заявка не найдена"),404
        old=c.execute("SELECT manager_note,next_contact FROM leads WHERE id=?",(lid,)).fetchone()
        if "manager_note" not in data:note=old["manager_note"] or ""
        if "next_contact" not in data:nxt=old["next_contact"] or ""
        c.execute("UPDATE leads SET status=?,manager_note=?,next_contact=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(status,note,nxt,lid))
    log("status","lead",lid,status)
    return jsonify(ok=True,status=status)

@app.get("/api/audit")
def audit():
    if not is_admin():return jsonify(error="unauthorized"),401
    with db() as c:r=c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 100").fetchall()
    return jsonify([dict(x) for x in r])

@app.errorhandler(404)
def not_found(e): return render_template("404.html"),404

@app.errorhandler(413)
def too_large(e): return jsonify(error="Файл слишком большой. Максимум 12 МБ за запрос."),413

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)
