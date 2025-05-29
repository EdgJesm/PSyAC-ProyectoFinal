import os
import hashlib
import sqlite3
from datetime import datetime
import argparse

class Sbac:
    def __init__(self, repo_path=None):
        self.repo_path = repo_path or os.getcwd()
        self.sbac_dir = os.path.join(self.repo_path, ".sbac")
        self.db_path = os.path.join(self.sbac_dir, "sbac.db")
        self.initialized = os.path.exists(self.sbac_dir)
        if self.initialized:
            self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabla de configuración
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        
        # Tabla de archivos rastreados
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            last_hash TEXT,
            last_modified REAL,
            staged INTEGER DEFAULT 0
        )
        """)
        
        # Tabla de commits
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS commits (
            id TEXT PRIMARY KEY,
            message TEXT,
            timestamp TEXT,
            parent_id TEXT
        )
        """)
        
        # Tabla de cambios en commits
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS commit_files (
            commit_id TEXT,
            file_path TEXT,
            file_hash TEXT,
            FOREIGN KEY(commit_id) REFERENCES commits(id)
        )
        """)
        
        # Tabla de baselines
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS baselines (
            name TEXT PRIMARY KEY,
            commit_id TEXT,
            FOREIGN KEY(commit_id) REFERENCES commits(id)
        )
        """)
        
        conn.commit()
        conn.close()

    def init(self):
        """Inicializa un nuevo repositorio"""
        if self.initialized:
            print(f"Ya existe un repositorio SBAC en {self.sbac_dir}")
            return False
        
        os.makedirs(self.sbac_dir)
        os.makedirs(os.path.join(self.sbac_dir, "objects"))
        self._init_db()
        
        # Guardar configuración inicial
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO config (key, value) VALUES (?, ?)",
            ("created_at", datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        
        self.initialized = True
        print(f"Repositorio SBAC inicializado en {self.repo_path}")
        return True

    def add(self, file_path):
        """Añade un archivo al área de staging"""
        if not self.initialized:
            print("Error: No se ha inicializado un repositorio")
            return False
        
        abs_path = os.path.join(self.repo_path, file_path)
        if not os.path.exists(abs_path):
            print(f"Error: El archivo {file_path} no existe")
            return False
        
        file_hash = self._calculate_hash(abs_path)
        last_modified = os.path.getmtime(abs_path)
        
        # Guardar el archivo en objetos
        self._store_object(file_hash, abs_path)
        
        # Registrar en la base de datos
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT OR REPLACE INTO files (path, last_hash, last_modified, staged) VALUES (?, ?, ?, 1)",
            (file_path, file_hash, last_modified)
        )
        
        conn.commit()
        conn.close()
        
        print(f"Archivo {file_path} añadido al staging area")
        return True

    def status(self):
        """Muestra el estado actual del repositorio"""
        if not self.initialized:
            print("Error: No se ha inicializado un repositorio")
            return False
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        print("\nEstado del repositorio:")
        print(f"Directorio del repositorio: {self.repo_path}")
        
        # Archivos en staging
        cursor.execute("SELECT path FROM files WHERE staged = 1")
        staged_files = [row[0] for row in cursor.fetchall()]
        
        # Archivos modificados
        cursor.execute("SELECT path, last_hash FROM files")
        modified_files = []
        for row in cursor.fetchall():
            path, last_hash = row
            abs_path = os.path.join(self.repo_path, path)
            if os.path.exists(abs_path) and self._calculate_hash(abs_path) != last_hash:
                modified_files.append(path)
        
        # Archivos no rastreados
        untracked_files = self._find_untracked_files()
        
        if staged_files:
            print("\nCambios a confirmar (staged):")
            for file in staged_files:
                print(f"  nuevo archivo: {file}")
        
        if modified_files:
            print("\nCambios no staged para commit:")
            for file in modified_files:
                print(f"  modificado: {file}")
        
        if untracked_files:
            print("\nArchivos no rastreados:")
            for file in untracked_files:
                print(f"  {file}")
        
        conn.close()
        return True

    def diff(self, file_path=None):
        """Muestra las diferencias en los archivos"""
        if not self.initialized:
            print("Error: No se ha inicializado un repositorio")
            return False
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if file_path:
            # Mostrar diff para un archivo específico
            cursor.execute("SELECT last_hash FROM files WHERE path = ?", (file_path,))
            row = cursor.fetchone()
            
            if not row:
                print(f"Error: El archivo {file_path} no está siendo rastreado")
                return False
            
            old_hash = row[0]
            old_content = self._get_object_content(old_hash).splitlines()
            
            abs_path = os.path.join(self.repo_path, file_path)
            with open(abs_path, "r") as f:
                new_content = f.read().splitlines()
            
            print(f"\nDiferencias para {file_path}:")
            for line in difflib.unified_diff(
                old_content, new_content, 
                fromfile=file_path, 
                tofile=file_path,
                lineterm=""
            ):
                print(line)
        else:
            # Mostrar diff para todos los archivos modificados
            cursor.execute("SELECT path, last_hash FROM files")
            for row in cursor.fetchall():
                path, last_hash = row
                abs_path = os.path.join(self.repo_path, path)
                
                if os.path.exists(abs_path):
                    current_hash = self._calculate_hash(abs_path)
                    if current_hash != last_hash:
                        old_content = self._get_object_content(last_hash).splitlines()
                        with open(abs_path, "r") as f:
                            new_content = f.read().splitlines()
                        
                        print(f"\nDiferencias para {path}:")
                        for line in difflib.unified_diff(
                            old_content, new_content, 
                            fromfile=path, 
                            tofile=path,
                            lineterm=""
                        ):
                            print(line)
        
        conn.close()
        return True

    def commit(self, message):
        """Crea un nuevo commit con los archivos en staging"""
        if not self.initialized:
            print("Error: No se ha inicializado un repositorio")
            return False

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Obtener el último commit (HEAD)
        cursor.execute("SELECT id FROM commits ORDER BY timestamp DESC LIMIT 1")
        parent = cursor.fetchone()
        parent_id = parent[0] if parent else None

        # Crear nuevo commit
        commit_id = hashlib.sha1(str(datetime.now()).encode()).hexdigest()
        cursor.execute(
            "INSERT INTO commits VALUES (?, ?, ?, ?)",
            (commit_id, message, str(datetime.now()), parent_id)
        )

        # Registrar archivos en staging
        cursor.execute("SELECT path, last_hash FROM files WHERE staged = 1")
        for path, file_hash in cursor.fetchall():
            cursor.execute(
                "INSERT INTO commit_files VALUES (?, ?, ?)",
                (commit_id, path, file_hash)
            )
            cursor.execute("UPDATE files SET staged = 0 WHERE path = ?", (path,))

        conn.commit()
        conn.close()
        print(f"Commit creado: {commit_id[:6]} - {message}")
        return True

    def history(self):
        """Muestra el historial de commits"""
        if not self.initialized:
            print("Error: No se ha inicializado un repositorio")
            return False

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, message, timestamp FROM commits 
        ORDER BY timestamp DESC
        """)
        print("\nHistorial de commits:")
        for commit_id, message, timestamp in cursor.fetchall():
            print(f"{commit_id[:6]} | {timestamp} | {message}")
        conn.close()

    def baseline(self, name):
        """Crea un baseline en el commit actual"""
        if not self.initialized:
            print("Error: No se ha inicializado un repositorio")
            return False

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM commits ORDER BY timestamp DESC LIMIT 1")
        commit = cursor.fetchone()
        if not commit:
            print("Error: No hay commits para crear baseline")
            return False
        
        cursor.execute(
            "INSERT OR REPLACE INTO baselines VALUES (?, ?)",
            (name, commit[0])
        )
        conn.commit()
        conn.close()
        print(f"Baseline '{name}' creada en commit {commit[0][:6]}")
        return True

    def list_baselines(self):
        """Lista todas las baselines"""
        if not self.initialized:
            print("Error: No se ha inicializado un repositorio")
            return False

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name, commit_id FROM baselines")
        print("\nBaselines disponibles:")
        for name, commit_id in cursor.fetchall():
            cursor.execute(
                "SELECT message FROM commits WHERE id = ?",
                (commit_id,)
            )
            message = cursor.fetchone()[0]
            print(f"{name} -> {commit_id[:6]} | {message}")
        conn.close()

    def checkout(self, version):
        """Restaura archivos a una versión específica"""
        if not self.initialized:
            print("Error: No se ha inicializado un repositorio")
            return False

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Verificar si es un baseline
        cursor.execute(
            "SELECT commit_id FROM baselines WHERE name = ?",
            (version,)
        )
        baseline = cursor.fetchone()
        if baseline:
            commit_id = baseline[0]
        else:
            commit_id = version  # Asumir que es un commit ID

        # Restaurar archivos
        cursor.execute("""
        SELECT file_path, file_hash FROM commit_files
        WHERE commit_id = ?
        """, (commit_id,))

        for path, file_hash in cursor.fetchall():
            object_path = os.path.join(
                self.sbac_dir, "objects", 
                file_hash[:2], file_hash[2:]
            )
            with open(object_path, "rb") as src, open(path, "wb") as dest:
                dest.write(src.read())
            print(f"Restaurado: {path}")

        conn.close()
        print(f"Checkout completado a versión: {version}")
        return True

    # Métodos auxiliares
    def _calculate_hash(self, file_path):
        """Calcula el hash SHA-1 de un archivo"""
        hasher = hashlib.sha1()
        with open(file_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                hasher.update(data)
        return hasher.hexdigest()

    def _store_object(self, object_hash, file_path):
        """Almacena un objeto en el sistema de archivos"""
        object_dir = os.path.join(self.sbac_dir, "objects", object_hash[:2])
        os.makedirs(object_dir, exist_ok=True)
        object_path = os.path.join(object_dir, object_hash[2:])
        
        with open(file_path, "rb") as src, open(object_path, "wb") as dest:
            dest.write(src.read())

    def _get_object_content(self, object_hash):
        """Obtiene el contenido de un objeto almacenado"""
        object_path = os.path.join(self.sbac_dir, "objects", object_hash[:2], object_hash[2:])
        with open(object_path, "r") as f:
            return f.read()

    def _find_untracked_files(self):
        """Encuentra archivos no rastreados"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT path FROM files")
        tracked_files = {row[0] for row in cursor.fetchall()}
        conn.close()
        
        untracked = []
        for root, dirs, files in os.walk(self.repo_path):
            if ".sbac" in dirs:
                dirs.remove(".sbac")
            
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), self.repo_path)
                if rel_path not in tracked_files:
                    untracked.append(rel_path)
        return untracked

def main():
    parser = argparse.ArgumentParser(description="SBAC - Sistema Básico de Control de Versiones")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Comandos originales
    init_parser = subparsers.add_parser("init", help="Inicializar un repositorio")
    init_parser.add_argument("path", nargs="?", default=".", help="Ruta donde inicializar el repositorio")
    
    add_parser = subparsers.add_parser("add", help="Añadir archivos al staging area")
    add_parser.add_argument("files", nargs="+", help="Archivos a añadir")
    
    subparsers.add_parser("status", help="Mostrar el estado del repositorio")
    
    diff_parser = subparsers.add_parser("diff", help="Mostrar diferencias")
    diff_parser.add_argument("file", nargs="?", help="Archivo específico para mostrar diferencias")

    # Comandos nuevos
    commit_parser = subparsers.add_parser("commit", help="Crear nuevo commit")
    commit_parser.add_argument("message", help="Mensaje descriptivo del commit")

    subparsers.add_parser("history", help="Mostrar historial de commits")

    baseline_parser = subparsers.add_parser("baseline", help="Crear baseline")
    baseline_parser.add_argument("name", help="Nombre de la baseline")

    subparsers.add_parser("list-baselines", help="Listar baselines")

    checkout_parser = subparsers.add_parser("checkout", help="Restaurar versión")
    checkout_parser.add_argument("version", help="Commit ID o nombre de baseline")

    args = parser.parse_args()
    sbac = Sbac(args.path if hasattr(args, "path") else ".")

    if args.command == "init":
        sbac.init()
    elif args.command == "add":
        for file in args.files:
            sbac.add(file)
    elif args.command == "status":
        sbac.status()
    elif args.command == "diff":
        sbac.diff(args.file if hasattr(args, "file") else None)
    elif args.command == "commit":
        sbac.commit(args.message)
    elif args.command == "history":
        sbac.history()
    elif args.command == "baseline":
        sbac.baseline(args.name)
    elif args.command == "list-baselines":
        sbac.list_baselines()
    elif args.command == "checkout":
        sbac.checkout(args.version)

if __name__ == "__main__":
    main()