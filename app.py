import os,sqlite3,secrets,datetime
from pathlib import Path
from flask import Flask,render_template,request,redirect,url_for,session,flash,jsonify
from werkzeug.security import check_password_hash,generate_password_hash
from werkzeug.utils import secure_filename
BASE=Path(__file__).parent; DB=Path(os.getenv('DB_PATH',BASE/'data.sqlite3')); UP=BASE/'static'/'uploads'; UP.mkdir(parents=True,exist_ok=True)
app=Flask(__name__);app.secret_key=os.getenv('SECRET_KEY') or secrets.token_hex(32);app.config.update(MAX_CONTENT_LENGTH=8*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','0')=='1')
PHONE=os.getenv('BUSINESS_PHONE',''); ADMIN=os.getenv('ADMIN_PASSWORD','')
def conn():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
def init():
 with conn() as c:
  c.execute('CREATE TABLE IF NOT EXISTS tools(id INTEGER PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL,description TEXT DEFAULT "",price INTEGER NOT NULL DEFAULT 0,deposit INTEGER NOT NULL DEFAULT 0,quantity INTEGER NOT NULL DEFAULT 1,status TEXT NOT NULL DEFAULT "available",image TEXT DEFAULT "",featured INTEGER DEFAULT 0)')
  c.execute('CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY,tool_id INTEGER,name TEXT,phone TEXT,days INTEGER,created TEXT,status TEXT DEFAULT "new")')
  c.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)')
  if not c.execute('SELECT COUNT(*) FROM tools').fetchone()[0]:
   for x in [('Перфоратор SDS-Plus','Перфораторы','Для бурения бетона и кирпича',3500,15000,3),('Отбойный молоток','Перфораторы','Демонтаж бетона и стяжки',6500,25000,2),('Болгарка 230 мм','Резка и шлифовка','Резка металла и камня',3000,12000,4),('Бетономешалка 180 л','Бетонные работы','Для раствора и бетона',6000,30000,2),('Виброплита','Бетонные работы','Уплотнение грунта и песка',9000,40000,1),('Генератор 5 кВт','Электрооборудование','Автономное электропитание',8500,40000,2),('Строительный пылесос','Уборка','Для строительной пыли',4000,18000,2),('Лазерный уровень','Измерение','Разметка стен и потолков',3000,15000,3)]:c.execute('INSERT INTO tools(name,category,description,price,deposit,quantity) VALUES(?,?,?,?,?,?)',x)
init()
def setting(key,default=''):
 with conn() as c:r=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone();return r['value'] if r else default
def tools():
 with conn() as c:return [dict(r) for r in c.execute('SELECT * FROM tools ORDER BY featured DESC,id DESC')]
def logged():return session.get('admin') is True
def csrf():return session.setdefault('csrf',secrets.token_urlsafe(24))
def guard():
 if not logged():return redirect('/admin/login')
 if request.method=='POST' and request.form.get('csrf')!=csrf():return ('CSRF error',403)
@app.context_processor
def ctx():return dict(csrf=csrf(),phone=setting('phone',PHONE),company=setting('company','Делай сам'),demo=True)
@app.after_request
def headers(r):
 r.headers['X-Content-Type-Options']='nosniff';r.headers['X-Frame-Options']='SAMEORIGIN';return r
@app.route('/')
def home():
 data=tools();q=request.args.get('q','').strip().lower();cat=request.args.get('category','');data=[t for t in data if (not q or q in (t['name']+' '+t['description']).lower()) and (not cat or t['category']==cat)];return render_template('home.html',tools=data,categories=sorted(set(t['category'] for t in tools())),q=q,category=cat)
@app.post('/request')
def order():
 if request.form.get('csrf')!=csrf():return ('CSRF error',403)
 try:tid=int(request.form['tool_id']);days=max(1,min(365,int(request.form['days'])));name=request.form['name'].strip()[:90];phone=request.form['phone'].strip()[:30]
 except (ValueError,KeyError):return ('Некорректные данные',400)
 if not name or len(phone)<7:return ('Заполните имя и телефон',400)
 with conn() as c:
  tool=c.execute('SELECT * FROM tools WHERE id=?',(tid,)).fetchone()
  if not tool or tool['status']!='available' or tool['quantity']<1:return ('Инструмент недоступен',400)
  c.execute('INSERT INTO requests(tool_id,name,phone,days,created) VALUES(?,?,?,?,?)',(tid,name,phone,days,datetime.datetime.now().isoformat(timespec='minutes')))
 return render_template('thanks.html',tool=dict(tool),days=days)
@app.route('/admin/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  if request.form.get('csrf')!=csrf():return ('CSRF error',403)
  if ADMIN and secrets.compare_digest(request.form.get('password',''),ADMIN):session.clear();session['admin']=True;csrf();return redirect('/admin')
  flash('Неверный пароль или пароль администратора не задан')
 return render_template('login.html')
@app.post('/admin/logout')
def logout():
 g=guard()
 if g:return g
 session.clear();return redirect('/')
@app.route('/admin')
def admin():
 g=guard()
 if g:return g
 with conn() as c:orders=[dict(r) for r in c.execute('SELECT requests.*,tools.name tool FROM requests LEFT JOIN tools ON tools.id=requests.tool_id ORDER BY requests.id DESC')]
 return render_template('admin.html',tools=tools(),orders=orders,company=setting('company','Делай сам'),phone=setting('phone',PHONE))
def image_upload():
 f=request.files.get('image')
 if not f or not f.filename:return None
 if f.filename.rsplit('.',1)[-1].lower() not in ('jpg','jpeg','png','webp'):raise ValueError('Разрешены JPG, PNG, WEBP')
 from PIL import Image
 from io import BytesIO
 try:
  im=Image.open(BytesIO(f.read()));im.verify();f.seek(0);im=Image.open(BytesIO(f.read()));im.thumbnail((1400,1400));im=im.convert('RGB')
 except Exception:raise ValueError('Неверный файл изображения')
 filename=secrets.token_hex(12)+'.webp';im.save(UP/filename,'WEBP',quality=82);return '/static/uploads/'+filename
@app.post('/admin/tool')
def save_tool():
 g=guard()
 if g:return g
 try:
  tid=int(request.form.get('id') or 0);name=request.form['name'].strip()[:120];category=request.form['category'].strip()[:70];price=max(0,int(request.form['price']));deposit=max(0,int(request.form.get('deposit') or 0));quantity=max(0,int(request.form.get('quantity') or 0));status=request.form.get('status','available');status=status if status in ('available','rented','service') else 'available';image=image_upload()
  if not name or not category:raise ValueError('Укажите название и категорию')
  with conn() as c:
   if tid:
    if image:c.execute('UPDATE tools SET name=?,category=?,description=?,price=?,deposit=?,quantity=?,status=?,image=? WHERE id=?',(name,category,request.form.get('description','')[:600],price,deposit,quantity,status,image,tid))
    else:c.execute('UPDATE tools SET name=?,category=?,description=?,price=?,deposit=?,quantity=?,status=? WHERE id=?',(name,category,request.form.get('description','')[:600],price,deposit,quantity,status,tid))
   else:c.execute('INSERT INTO tools(name,category,description,price,deposit,quantity,status,image) VALUES(?,?,?,?,?,?,?,?)',(name,category,request.form.get('description','')[:600],price,deposit,quantity,status,image or ''))
  flash('Инструмент сохранён')
 except (ValueError,KeyError) as e:flash('Ошибка: '+str(e))
 return redirect('/admin#catalog')
@app.post('/admin/delete/<int:tid>')
def delete(tid):
 g=guard()
 if g:return g
 with conn() as c:c.execute('DELETE FROM tools WHERE id=?',(tid,))
 flash('Инструмент удалён');return redirect('/admin#catalog')
@app.post('/admin/order/<int:oid>')
def order_status(oid):
 g=guard()
 if g:return g
 status=request.form.get('status');
 if status not in ('new','confirmed','completed','cancelled'):return ('Bad status',400)
 with conn() as c:c.execute('UPDATE requests SET status=? WHERE id=?',(status,oid))
 return redirect('/admin#orders')
@app.post('/admin/settings')
def settings():
 g=guard()
 if g:return g
 with conn() as c:
  for key in ('company','phone'):c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,request.form.get(key,'').strip()[:100]))
 flash('Настройки сохранены');return redirect('/admin#settings')
if __name__=='__main__':app.run(debug=False,port=int(os.getenv('PORT','5000')))
