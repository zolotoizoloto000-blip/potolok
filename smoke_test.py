import os
os.environ["COOKIE_SECURE"]="0"; os.environ["ADMIN_PASSWORD"]="test-password"
import app as A
c=A.app.test_client()
tests=[("root",c.get("/"),302),("ru",c.get("/ru/"),200),("kk",c.get("/kk/"),200),("en",c.get("/en/"),200),("sitemap",c.get("/sitemap.xml"),200),("robots",c.get("/robots.txt"),200),("404",c.get("/not-found/"),404),("login page",c.get("/admin/login"),200)]
r=c.post("/admin/login",data={"password":"test-password"}); tests.append(("login",r,302)); tests.append(("admin",c.get("/admin"),200))
for n,r,e in tests: print(n,r.status_code,e)
assert all(r.status_code==e for _,r,e in tests)
print("SMOKE TESTS PASSED")
