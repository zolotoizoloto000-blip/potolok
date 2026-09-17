
import os, sqlite3, re
DATABASE_URL=os.getenv("DATABASE_URL","")
IS_PG=bool(DATABASE_URL)

class Conn:
    def __init__(self):
        if IS_PG:
            import psycopg
            from psycopg.rows import dict_row
            self.c=psycopg.connect(DATABASE_URL,row_factory=dict_row)
        else:
            self.c=sqlite3.connect(os.getenv("SQLITE_PATH") or os.path.join(os.getenv("DATA_DIR",os.path.dirname(__file__)),"catalog.db"))
            self.c.row_factory=sqlite3.Row
    def __enter__(self): return self
    def __exit__(self,t,v,tb):
        if t is None:self.c.commit()
        else:self.c.rollback()
        self.c.close()
    def _sql(self,s):
        if IS_PG:
            s=s.replace("?","%s")
            s=s.replace("DATETIME DEFAULT CURRENT_TIMESTAMP","TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            s=s.replace("INTEGER PRIMARY KEY AUTOINCREMENT","SERIAL PRIMARY KEY")
        return s
    def execute(self,s,args=()):
        return self.c.execute(self._sql(s),args)
    def executescript(self,s):
        if IS_PG:
            for q in [x.strip() for x in s.split(";") if x.strip()]: self.c.execute(self._sql(q))
        else:self.c.executescript(s)
