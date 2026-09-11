from argon2 import PasswordHasher

from src.config.mysql_connection import get_mysql_connection

ph = PasswordHasher()


class Usuario:
    @staticmethod
    def inicializar_tabla():
        connection = get_mysql_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS usuario (
                        idusuario INT PRIMARY KEY AUTO_INCREMENT,
                        usuario VARCHAR(80) NOT NULL UNIQUE,
                        password_hash VARCHAR(255) NOT NULL
                    )
                    """
                )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def registrar(usuario, password):
        connection = get_mysql_connection()
        try:
            with connection.cursor(dictionary=True) as cursor:
                cursor.execute('SELECT idusuario FROM usuario WHERE usuario = %s', (usuario,))
                if cursor.fetchone():
                    raise ValueError('El usuario ya existe.')
                cursor.execute(
                    'INSERT INTO usuario (usuario, password_hash) VALUES (%s, %s)',
                    (usuario, ph.hash(password)),
                )
            connection.commit()
            return True
        finally:
            connection.close()

    @staticmethod
    def autenticar(usuario, password):
        connection = get_mysql_connection()
        try:
            with connection.cursor(dictionary=True) as cursor:
                cursor.execute('SELECT * FROM usuario WHERE usuario = %s', (usuario,))
                usuario_db = cursor.fetchone()
            if not usuario_db:
                return None
            try:
                if ph.verify(usuario_db['password_hash'], password):
                    return usuario_db
            except Exception:
                return None
            return None
        finally:
            connection.close()
