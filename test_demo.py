"""Run: COOKIE_SECURE=0 ADMIN_PASSWORD=qa-secret python test_demo.py (isolated database recommended)."""
import os
os.environ.setdefault("COOKIE_SECURE","0")
os.environ.setdefault("ADMIN_PASSWORD","qa-secret")
import app as m
c=m.app.test_client()
assert c.get("/ru/").status_code==200
assert c.get("/kk/").status_code==200
assert c.get("/en/").status_code==200
assert c.get("/admin").status_code==302
assert c.get("/api/products?all=1").status_code==401
assert c.post("/api/leads",data={"name":"","phone":"123"}).status_code==400
assert c.post("/admin/login",data={"password":"qa-secret"}).status_code==302
with c.session_transaction() as sess: csrf=sess["csrf"]
r=c.post("/api/categories",json={"slug":"test-category","title_ru":"Тестовая категория"},headers={"X-CSRF-Token":csrf})
assert r.status_code==201,r.data
cat=r.get_json();assert cat["slug"]=="test-category"
r=c.post("/api/products",data={"name_ru":"Тестовый профиль","status":"Черновик"},headers={"X-CSRF-Token":csrf})
assert r.status_code==201,r.data
p=r.get_json();assert p["slug"] and p["status"]=="Черновик"
assert not any(x["id"]==p["id"] for x in c.get("/api/products").get_json())
assert any(x["id"]==p["id"] for x in c.get("/api/products?all=1").get_json())
r=c.put(f"/api/products/{p['id']}",data={"name_ru":"Профиль тест обновлён","status":"Опубликован"},headers={"X-CSRF-Token":csrf})
assert r.status_code==200,r.data
assert any(x["id"]==p["id"] for x in c.get("/api/products").get_json())
r=c.post("/api/leads",data={"name":"Тест","phone":"+7 777 123 45 67","message":"Тестовая заявка","source":"qa"})
assert r.status_code==201,r.data
lead=next(x for x in c.get("/api/leads").get_json() if x["source"]=="qa")
r=c.put(f"/api/leads/{lead['id']}",json={"status":"Продажа","manager_note":"Тест"},headers={"X-CSRF-Token":csrf})
assert r.status_code==200,r.data
assert next(x for x in c.get("/api/leads").get_json() if x["id"]==lead["id"])["status"]=="Продажа"
assert c.delete(f"/api/products/{p['id']}",headers={"X-CSRF-Token":csrf}).status_code==200
assert c.delete(f"/api/categories/{cat['id']}",headers={"X-CSRF-Token":csrf}).status_code==200
print("PASS: pages, auth, draft/publish, CRUD, lead, CRM status")
