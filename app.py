
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
DATA_DIR=Path(os.environ.get("DATA_DIR", str(BASE))).resolve()
UPLOAD=Path(os.environ.get("UPLOAD_DIR", str(DATA_DIR/"uploads"))).resolve(); UPLOAD.mkdir(parents=True,exist_ok=True)
DB=Path(os.environ.get("SQLITE_PATH", str(DATA_DIR/"catalog.db"))).resolve()
app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE","1")=="1")
app.config["MAX_CONTENT_LENGTH"]=12*1024*1024
ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD","")
ADMIN_HASH=os.environ.get("ADMIN_PASSWORD_HASH","")
SITE_URL=os.environ.get("SITE_URL","").rstrip("/")
ALLOWED={"jpg","jpeg","png","webp","bmp","tif","tiff","gif","avif","heic","heif"}

@app.after_request
def security_headers(response):
    """Safe defaults for both the public site and the admin panel."""
    response.headers.setdefault("X-Content-Type-Options","nosniff")
    response.headers.setdefault("X-Frame-Options","SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy","strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy","camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; font-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self' https://wa.me")
    if (SITE_URL.startswith("https://") or os.getenv("FORCE_HTTPS","0")=="1"):
        response.headers.setdefault("Strict-Transport-Security","max-age=31536000; includeSubDomains")
    if request.path.startswith("/admin") or request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control","no-store")
        response.headers.setdefault("X-Robots-Tag","noindex, nofollow, noarchive")
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
          category TEXT, category_id INTEGER, brand TEXT, price REAL, unit TEXT, old_price REAL,
          seo_title_ru TEXT, seo_title_kz TEXT, seo_title_en TEXT, seo_description_ru TEXT, seo_description_kz TEXT, seo_description_en TEXT,
          stock TEXT, sku TEXT, status TEXT DEFAULT 'Опубликован',
          ask_price INTEGER DEFAULT 0, featured INTEGER DEFAULT 0, new_item INTEGER DEFAULT 0,
          photos TEXT DEFAULT '[]', sort_order INTEGER DEFAULT 0,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS leads(
          id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, source TEXT, name TEXT, phone TEXT,
          message TEXT, status TEXT DEFAULT 'Новая', manager_note TEXT, next_contact TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS categories(
          id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE, title_ru TEXT, title_kz TEXT, title_en TEXT, sort_order INTEGER DEFAULT 0,
          seo_title_ru TEXT, seo_title_kz TEXT, seo_title_en TEXT, seo_description_ru TEXT, seo_description_kz TEXT, seo_description_en TEXT);
        CREATE TABLE IF NOT EXISTS audit_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, entity TEXT, entity_id INTEGER, detail TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS site_settings(
          key TEXT PRIMARY KEY, value TEXT DEFAULT '', updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS login_security(
          ip_hash TEXT PRIMARY KEY, attempts INTEGER DEFAULT 0, window_start REAL DEFAULT 0, blocked_until REAL DEFAULT 0);
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
def migrate_catalog_v44():
    product_cols=[("category_id","INTEGER"),("seo_title_ru","TEXT"),("seo_title_kz","TEXT"),("seo_title_en","TEXT"),("seo_description_ru","TEXT"),("seo_description_kz","TEXT"),("seo_description_en","TEXT")]
    category_cols=[("seo_title_ru","TEXT"),("seo_title_kz","TEXT"),("seo_title_en","TEXT"),("seo_description_ru","TEXT"),("seo_description_kz","TEXT"),("seo_description_en","TEXT")]
    with db() as c:
        if DATABASE_URL:
            for n,t in product_cols:
                try:c.execute(f"ALTER TABLE products ADD COLUMN IF NOT EXISTS {n} {t}")
                except:pass
            for n,t in category_cols:
                try:c.execute(f"ALTER TABLE categories ADD COLUMN IF NOT EXISTS {n} {t}")
                except:pass
        else:
            pcols={r["name"] for r in c.execute("PRAGMA table_info(products)")}
            ccols={r["name"] for r in c.execute("PRAGMA table_info(categories)")}
            for n,t in product_cols:
                if n not in pcols:c.execute(f"ALTER TABLE products ADD COLUMN {n} {t}")
            for n,t in category_cols:
                if n not in ccols:c.execute(f"ALTER TABLE categories ADD COLUMN {n} {t}")
        # one-time link old text categories to stable IDs
        c.execute("UPDATE products SET category_id=(SELECT id FROM categories WHERE categories.title_ru=products.category LIMIT 1) WHERE category_id IS NULL AND category<>''")
migrate_catalog_v44()

def seed_delai_sam_catalog():
    """Populate a useful rental demo catalogue without overwriting owner-created tools."""
    categories = [
      ("perforatory","Перфораторы","Перфораторлар","Rotary hammers"),
      ("shlifmashiny","Шлифмашины","Тегістеуіштер","Grinders"),
      ("pily","Пилы","Аралар","Saws"),
      ("beton","Бетонные работы","Бетон жұмыстары","Concrete tools"),
      ("sad","Садовая техника","Бақша техникасы","Garden tools"),
      ("lestnicy","Лестницы и прочее","Сатылар және басқа","Ladders & more"),
    ]
    products = [
      ("Перфоратор SDS+", "SDS+ перфораторы", "SDS+ rotary hammer", "perforatory", "Bosch", 5000, "сутки", "В наличии", "Сверление бетона, кирпича и демонтаж. Компактный вариант для ремонта.", "Бетон мен кірпішті бұрғылау және демонтаж жұмыстарына арналған.", "For drilling concrete and masonry and light demolition."),
      ("Перфоратор SDS Max", "SDS Max перфораторы", "SDS Max rotary hammer", "perforatory", "Makita", 8000, "сутки", "В наличии", "Мощный перфоратор для тяжёлого бурения и демонтажных работ.", "Ауыр бұрғылау және демонтаж жұмыстарына арналған қуатты құрал.", "Heavy-duty rotary hammer for drilling and demolition."),
      ("УШМ 125 мм", "125 мм бұрыштық тегістеуіш", "125 mm angle grinder", "shlifmashiny", "DeWalt", 3500, "сутки", "В наличии", "Для резки и шлифовки металла, плитки и других материалов.", "Металл, плитка және басқа материалдарды кесу мен тегістеуге арналған.", "For cutting and grinding metal, tile and other materials."),
      ("УШМ 230 мм", "230 мм бұрыштық тегістеуіш", "230 mm angle grinder", "shlifmashiny", "Bosch", 5000, "сутки", "В наличии", "Большая болгарка для интенсивной резки металла и камня.", "Металл мен тасты қарқынды кесуге арналған үлкен тегістеуіш.", "Large grinder for intensive cutting of metal and stone."),
      ("Дисковая пила", "Дискілі ара", "Circular saw", "pily", "Makita", 5000, "сутки", "В наличии", "Точный прямой рез древесины, фанеры и листовых материалов.", "Ағашты, фанераны және табақ материалдарды дәл кесуге арналған.", "For accurate straight cuts in timber, plywood and sheet materials."),
      ("Торцовочная пила", "Торцовкалық ара", "Mitre saw", "pily", "DeWalt", 8000, "сутки", "Под заказ", "Для точного поперечного и углового распила доски и профиля.", "Тақтай мен профильді дәл көлденең және бұрышпен кесуге арналған.", "For precise crosscuts and angled cuts in timber and profiles."),
      ("Бетономешалка 180 л", "180 л бетон араластырғыш", "180 L concrete mixer", "beton", "ProCraft", 7000, "сутки", "В наличии", "Для приготовления бетона и строительных растворов прямо на объекте.", "Нысанда бетон мен құрылыс қоспаларын дайындауға арналған.", "For mixing concrete and mortar directly on site."),
      ("Вибратор для бетона", "Бетон вибраторы", "Concrete vibrator", "beton", "Vektor", 6000, "сутки", "В наличии", "Уплотнение свежего бетона при заливке фундаментов, колонн и перекрытий.", "Іргетас, бағана және жабын құю кезінде бетонды тығыздауға арналған.", "Compacts fresh concrete in foundations, columns and slabs."),
      ("Триммер бензиновый", "Бензинді триммер", "Petrol trimmer", "sad", "Huter", 6000, "сутки", "В наличии", "Покос травы и расчистка участка. Подходит для дачи и территории вокруг дома.", "Шөп шабу және аумақты тазалауға арналған.", "For mowing grass and clearing garden areas."),
      ("Бензопила", "Бензин ара", "Chainsaw", "sad", "Stihl", 7000, "сутки", "В наличии", "Для распила древесины, веток и строительного бруса.", "Ағаш, бұтақ және құрылыс бөренелерін кесуге арналған.", "For cutting timber, branches and construction lumber."),
      ("Стремянка 3 м", "3 м баспалдақ", "3 m stepladder", "lestnicy", "Alumet", 3500, "сутки", "В наличии", "Устойчивая алюминиевая стремянка для монтажных и отделочных работ.", "Монтаж және әрлеу жұмыстарына арналған тұрақты алюминий саты.", "Stable aluminium stepladder for installation and finishing work."),
      ("Пылесос строительный", "Құрылыс шаңсорғышы", "Construction vacuum", "lestnicy", "Karcher", 5000, "сутки", "В наличии", "Сбор строительной пыли и мусора во время ремонта и монтажа.", "Жөндеу кезінде құрылыс шаңы мен қоқысты жинауға арналған.", "For collecting construction dust and debris during renovation."),
    ]
    with db() as c:
        existing_cats={r["slug"]:r["id"] for r in c.execute("SELECT id,slug FROM categories").fetchall()}
        order=0
        for slug,ru,kz,en in categories:
            if slug not in existing_cats:
                c.execute("INSERT INTO categories(slug,title_ru,title_kz,title_en,sort_order) VALUES(?,?,?,?,?)",(slug,ru,kz,en,order))
                row=c.execute("SELECT id FROM categories WHERE slug=?",(slug,)).fetchone(); existing_cats[slug]=row["id"]
            order+=1
        # Add demo tools only when this catalogue has not been seeded before.
        already=c.execute("SELECT 1 FROM products WHERE sku LIKE 'DS-DEMO-%' LIMIT 1").fetchone()
        if already: return
        for i,(ru,kz,en,cat,brand,price,unit,stock,dru,dkz,den) in enumerate(products,1):
            slug=slugify(ru)
            base=slug;n=2
            while c.execute("SELECT 1 FROM products WHERE slug=?",(slug,)).fetchone(): slug=f"{base}-{n}"; n+=1
            cid=existing_cats[cat]
            cat_ru=next(x[1] for x in categories if x[0]==cat)
            c.execute("""INSERT INTO products(slug,name_ru,name_kz,name_en,description_ru,description_kz,description_en,specs_ru,specs_kz,specs_en,category,category_id,brand,price,unit,stock,sku,status,featured,new_item,photos,sort_order)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'Опубликован',?,?,?,?)""",
                      (slug,ru,kz,en,dru,dkz,den,"Цена указана для демо. Условия и залог уточняйте у менеджера.","Баға демо үшін көрсетілген. Шарттар мен кепілді менеджерден нақтылаңыз.","Demo price. Confirm terms and deposit with the manager.",cat_ru,cid,brand,price,unit,stock,f"DS-DEMO-{i:02d}",1 if i<=4 else 0,1 if i in (2,7,9) else 0,"[]",i))
seed_delai_sam_catalog()

DEFAULT_SETTINGS={
 "hero_eyebrow":"Алматы · прокат строительного инструмента",
 "hero_title":"Инструмент для ремонта и стройки — без лишних покупок.",
 "hero_text":"Выберите нужный инструмент, посмотрите стоимость аренды и отправьте заявку. Для демонстрации цены и позиции можно изменить через админ-панель.",
 "catalog_title":"Каталог инструмента",
 "catalog_text":"Выберите категорию и инструмент. Актуальное наличие и итоговую стоимость аренды подтверждает менеджер.",
 "site_background_image":"",
 "phone":"+7 706 606 14 54", "whatsapp":"77066061454",
 "address":"Алматы, ул. Фаризы Онгарсыновой, 204/1", "gis_url":"", "instagram_url":"",
 "faq1_q":"Как арендовать инструмент?", "faq1_a":"Выберите инструмент в каталоге и отправьте заявку. Менеджер подтвердит наличие, срок и условия выдачи.",
 "faq2_q":"Можно арендовать на несколько дней?", "faq2_a":"Да. Укажите нужный срок — менеджер рассчитает итоговую стоимость.",
 "faq3_q":"Как узнать, свободен ли инструмент?", "faq3_a":"Статус отображается в каталоге, а актуальное наличие подтверждается при оформлении заявки.",
 "faq4_q":"Можно ли забронировать заранее?", "faq4_a":"Да. Оставьте заявку с желаемыми датами, чтобы менеджер подтвердил бронь.",
 "faq5_q":"", "faq5_a":"", "faq6_q":"", "faq6_a":"", "faq7_q":"", "faq7_a":"", "faq8_q":"", "faq8_a":"", "faq9_q":"", "faq9_a":"", "faq10_q":"", "faq10_a":"", "faq11_q":"", "faq11_a":"", "faq12_q":"", "faq12_a":"",
 "seo_title_ru":"Делай сам — прокат строительного инструмента в Алматы",
 "seo_description_ru":"Прокат строительного инструмента в Алматы: каталог, цены аренды, наличие и заявка онлайн.",
 "seo_title_kz":"Делай сам — Алматыда құрылыс құралдарын жалға беру",
 "seo_description_kz":"Алматыда құрылыс құралдарын жалға беру: каталог, жалға алу бағасы, қолжетімділік және онлайн өтінім.",
 "seo_title_en":"Delai Sam — construction tool rental in Almaty",
 "seo_description_en":"Construction tool rental in Almaty: catalogue, rental prices, availability and online requests."
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
      "specs":d.get(f"specs_{lang}") or d.get("specs_ru",""),
      "seo_title":d.get(f"seo_title_{lang}") or d.get("seo_title_ru","") or d.get(f"name_{lang}") or d.get("name_ru",""),
      "seo_description":d.get(f"seo_description_{lang}") or d.get("seo_description_ru","") or d.get(f"description_{lang}") or d.get("description_ru","")
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
    return "/uploads/"+name

def delete_image_url(u):
    if u.startswith("/uploads/"):
        try:(UPLOAD/u.rsplit("/",1)[-1]).unlink(missing_ok=True)
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

@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD, filename, max_age=86400)

@app.context_processor
def inject(): return {"csrf_token":csrf(),"site_url":SITE_URL}

@app.route("/admin/login", methods=["GET","POST"], strict_slashes=False)
def login():
    ip=request.headers.get("X-Forwarded-For",request.remote_addr or "").split(",")[0].strip()
    ip_hash=hashlib.sha256((ip+app.secret_key[:16]).encode()).hexdigest()
    now=time.time()
    with db() as c:
        rec=c.execute("SELECT * FROM login_security WHERE ip_hash=?",(ip_hash,)).fetchone()
    if rec and float(rec["blocked_until"] or 0)>now:
        return render_template("login.html",error="Слишком много попыток. Повторите через 15 минут."),429
    if request.method=="POST":
        if not secrets.compare_digest(request.form.get("csrf",""),session.get("csrf",csrf())):
            abort(400)
        if verify_password(request.form.get("password","")):
            session.clear();session["admin"]=True;session["csrf"]=secrets.token_urlsafe(24)
            with db() as c:c.execute("DELETE FROM login_security WHERE ip_hash=?",(ip_hash,))
            log("login","admin",detail=ip);return redirect("/admin")
        attempts=1; window_start=now
        if rec and now-float(rec["window_start"] or 0)<900:
            attempts=int(rec["attempts"] or 0)+1; window_start=float(rec["window_start"] or now)
        blocked=now+900 if attempts>=8 else 0
        with db() as c:
            c.execute("INSERT INTO login_security(ip_hash,attempts,window_start,blocked_until) VALUES(?,?,?,?) ON CONFLICT(ip_hash) DO UPDATE SET attempts=excluded.attempts,window_start=excluded.window_start,blocked_until=excluded.blocked_until",(ip_hash,attempts,window_start,blocked))
        return render_template("login.html",error="Слишком много попыток. Повторите через 15 минут." if blocked else "Неверный пароль"),429 if blocked else 401
    csrf()
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
    with db() as c:
        r=c.execute("SELECT * FROM products WHERE slug=? AND status='Опубликован'",(slug,)).fetchone()
        if not r:abort(404)
        similar=c.execute("SELECT * FROM products WHERE status='Опубликован' AND id<>? AND ((category_id IS NOT NULL AND category_id=?) OR (category_id IS NULL AND category=?)) ORDER BY featured DESC,id DESC LIMIT 3",(r["id"],r["category_id"],r["category"])).fetchall()
    return render_template("product.html",lang=lang,p=localized(row_product(r),lang),similar=[localized(row_product(x),lang) for x in similar],settings=get_settings())


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
        c.execute("INSERT INTO categories(slug,title_ru,title_kz,title_en,sort_order,seo_title_ru,seo_title_kz,seo_title_en,seo_description_ru,seo_description_kz,seo_description_en) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(sl,data.get("title_ru",""),data.get("title_kz",""),data.get("title_en",""),data.get("sort_order",0),data.get("seo_title_ru",""),data.get("seo_title_kz",""),data.get("seo_title_en",""),data.get("seo_description_ru",""),data.get("seo_description_kz",""),data.get("seo_description_en","")))
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
        c.execute("UPDATE categories SET slug=?,title_ru=?,title_kz=?,title_en=?,sort_order=?,seo_title_ru=?,seo_title_kz=?,seo_title_en=?,seo_description_ru=?,seo_description_kz=?,seo_description_en=? WHERE id=?",(sl,ru,data.get("title_kz",ru),data.get("title_en",ru),data.get("sort_order",old["sort_order"]),data.get("seo_title_ru",""),data.get("seo_title_kz",""),data.get("seo_title_en",""),data.get("seo_description_ru",""),data.get("seo_description_kz",""),data.get("seo_description_en",""),cid))
        c.execute("UPDATE products SET category=? WHERE category_id=? OR (category_id IS NULL AND category=?)",(ru,cid,old["title_ru"]))
        r=c.execute("SELECT * FROM categories WHERE id=?",(cid,)).fetchone()
    log("update","category",cid,ru);return jsonify(dict(r))

@app.delete("/api/categories/<int:cid>")
def del_category(cid):
    if not is_admin():return jsonify(error="unauthorized"),401
    require_csrf(); mode=request.args.get("mode","")
    with db() as c:
        old=c.execute("SELECT * FROM categories WHERE id=?",(cid,)).fetchone()
        if not old:return jsonify(error="not found"),404
        count=c.execute("SELECT COUNT(*) AS n FROM products WHERE category_id=? OR (category_id IS NULL AND category=?)",(cid,old["title_ru"])).fetchone()["n"]
        if count and mode!="detach": return jsonify(error="category_has_products",count=count),409
        if count:c.execute("UPDATE products SET category='',category_id=NULL WHERE category_id=? OR (category_id IS NULL AND category=?)",(cid,old["title_ru"]))
        c.execute("DELETE FROM categories WHERE id=?",(cid,))
    log("delete","category",cid);return jsonify(ok=True,detached=count)

@app.get("/<lang>/category/<slug>")
def category_page(lang,slug):
    if lang not in ("ru","kk","en"):abort(404)
    with db() as c:
        cat=c.execute("SELECT * FROM categories WHERE slug=?",(slug,)).fetchone()
        if not cat:abort(404)
        title=cat["title_"+("kz" if lang=="kk" else lang)] or cat["title_ru"]
        rows=c.execute("SELECT * FROM products WHERE status='Опубликован' AND (category_id=? OR (category_id IS NULL AND category=?)) ORDER BY featured DESC,sort_order,id DESC",(cat["id"],cat["title_ru"])).fetchall()
        lk="kz" if lang=="kk" else lang
        seo_title=cat[f"seo_title_{lk}"] or title+" | Центр Потолков Алматы"
        seo_description=cat[f"seo_description_{lk}"] or title+" — каталог Центр Потолков в Алматы. Фото, характеристики и актуальные предложения."
    return render_template("category.html",lang=lang,title=title,slug=slug,products=[localized(row_product(r),lang) for r in rows],settings=get_settings(),seo_title=seo_title,seo_description=seo_description)

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
      category=g("category"),category_id=int(g("category_id","0") or 0) or None,brand=g("brand"),price=num("price"),unit=g("unit"),old_price=num("old_price"),
      seo_title_ru=g("seo_title_ru"),seo_title_kz=g("seo_title_kz"),seo_title_en=g("seo_title_en"),seo_description_ru=g("seo_description_ru"),seo_description_kz=g("seo_description_kz"),seo_description_en=g("seo_description_en"),
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
