import os
import hashlib
import sqlite3
import difflib
from pathlib import Path
from datetime import datetime
import argparse


class MiniGit:
    def __init__(self, repo_path=None):
        self.repo_path = repo_path or os.getcwd()
        self.git_dir = os.path.join(self.repo_path, ".minigit")
        self.db_path = os.path.join(self.git_dir, "minigit.db")

        if not os.path.exists(self.git_dir):
            self.initialized = False
        else:
            self.initialized = True
            self._init_db()

    def init(self):
        """Inicializa un nuevo repositorio"""
        if self.initialized:
            print(f"Ya existe un repositorio MiniGit en {self.git_dir}")
            return False

        os.makedirs(self.git_dir)
        os.makedirs(os.path.join(self.git_dir, "objects"))
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
        print(f"Repositorio MiniGit inicializado en {self.repo_path}")
        return True

    def _init_db(self):
        """Inicializa la base de datos SQLite"""
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
        CREATE TABLE IF NOT EXISTS commit_changes (
            commit_id TEXT,
            file_path TEXT,
            file_hash TEXT,
            FOREIGN KEY(commit_id) REFERENCES commits(id),
            PRIMARY KEY (commit_id, file_path)
        )
        """)

        conn.commit()
        conn.close()

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

    def _calculate_hash(self, file_path):
        """Calcula el hash SHA-1 de un archivo"""
        hasher = hashlib.sha1()
        with open(file_path, "rb") as f:
            while True:
                data = f.read(65536)  # leer en bloques de 64KB
                if not data:
                    break
                hasher.update(data)
        return hasher.hexdigest()

    def _store_object(self, object_hash, file_path):
        """Almacena un objeto en el sistema de archivos"""
        object_dir = os.path.join(self.git_dir, "objects", object_hash[:2])
        os.makedirs(object_dir, exist_ok=True)
        object_path = os.path.join(object_dir, object_hash[2:])

        with open(file_path, "rb") as src, open(object_path, "wb") as dest:
            dest.write(src.read())

    def _get_object_content(self, object_hash):
        """Obtiene el contenido de un objeto almacenado"""
        object_path = os.path.join(self.git_dir, "objects", object_hash[:2], object_hash[2:])
        with open(object_path, "r") as f:
            return f.read()

    def _find_untracked_files(self):
        """Encuentra archivos en el directorio que no están siendo rastreados"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT path FROM files")
        tracked_files = {row[0] for row in cursor.fetchall()}
        conn.close()

        untracked = []
        for root, dirs, files in os.walk(self.repo_path):
            # Ignorar el directorio .minigit
            if ".minigit" in dirs:
                dirs.remove(".minigit")

            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), self.repo_path)
                if rel_path not in tracked_files:
                    untracked.append(rel_path)
        return untracked


def main():
    parser = argparse.ArgumentParser(description="MiniGit - Un sistema de control de versiones simplificado")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Comando init
    init_parser = subparsers.add_parser("init", help="Inicializar un nuevo repositorio")
    init_parser.add_argument("path", nargs="?", default=".", help="Ruta donde inicializar el repositorio")

    # Comando add
    add_parser = subparsers.add_parser("add", help="Añadir archivos al staging area")
    add_parser.add_argument("files", nargs="+", help="Archivos a añadir")

    # Comando status
    subparsers.add_parser("status", help="Mostrar el estado del repositorio")

    # Comando diff
    diff_parser = subparsers.add_parser("diff", help="Mostrar diferencias")
    diff_parser.add_argument("file", nargs="?", help="Archivo específico para mostrar diferencias")

    args = parser.parse_args()

    git = MiniGit(args.path if hasattr(args, "path") else ".")

    if args.command == "init":
        git.init()
    elif args.command == "add":
        for file in args.files:
            git.add(file)
    elif args.command == "status":
        git.status()
    elif args.command == "diff":
        git.diff(args.file if hasattr(args, "file") else None)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()