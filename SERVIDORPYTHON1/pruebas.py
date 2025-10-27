import sqlite3

db_path = r"D:\BCRPML2\PYTHON\DB\last_value.sqlite"

con = sqlite3.connect(db_path)
cur = con.cursor()

# Listar tablas
cur.execute("SELECT DISTINCT dp_id FROM last_value LIMIT 10")
print(cur.fetchall())


# Hacer la consulta si la tabla existe
cur.execute("""
    SELECT * FROM last_value
    WHERE dp_id = 10
    ORDER BY system_time DESC
    LIMIT 1
""")
print(cur.fetchone())

con.close()
