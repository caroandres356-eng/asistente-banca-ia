import sqlite3

DB_PATH = "banco.db"

def conectar():
    return sqlite3.connect(DB_PATH)

def crear_base():
    """Reconstruye banco.db desde cero con datos ficticios."""
    with conectar() as c:
        c.executescript("""
        DROP TABLE IF EXISTS clientes;
        DROP TABLE IF EXISTS tarjetas;
        DROP TABLE IF EXISTS auditoria;
        DROP TABLE IF EXISTS consultas;

        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL
        );
        CREATE TABLE tarjetas (
            id INTEGER PRIMARY KEY,
            cliente_id INTEGER NOT NULL REFERENCES clientes(id),
            ultimos4 TEXT NOT NULL,
            tipo TEXT NOT NULL,
            estado TEXT NOT NULL
        );
        CREATE TABLE auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            cliente_id INTEGER,
            accion TEXT,
            tarjeta_id INTEGER,
            aprobado_por TEXT,
            resultado TEXT
        );
        CREATE TABLE consultas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            cliente_id INTEGER,
            pregunta TEXT,
            intencion TEXT,
            mejor_distancia REAL,
            respondida INTEGER,
            latencia_ms INTEGER
        );

        INSERT INTO clientes VALUES (1, 'Ana Torres'), (2, 'Luis Rojas');
        INSERT INTO tarjetas VALUES
            (1, 1, '4821', 'debito',  'activa'),
            (2, 1, '7733', 'credito', 'activa'),
            (3, 2, '1190', 'credito', 'activa');
        """)

if __name__ == "__main__":
    crear_base()
    with conectar() as c:
        print(c.execute("SELECT * FROM tarjetas").fetchall())