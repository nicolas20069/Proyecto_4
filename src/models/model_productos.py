from decimal import Decimal

from src.config.mysql_connection import get_mysql_connection


class Producto:
  @staticmethod
  def inicializar_tabla():
    connection = get_mysql_connection()
    try:
      with connection.cursor() as cursor:
        cursor.execute(
          """
          CREATE TABLE IF NOT EXISTS producto (
            idproducto INT PRIMARY KEY AUTO_INCREMENT,
            producto VARCHAR(200) NOT NULL,
            marca VARCHAR(200) NOT NULL,
            precio DECIMAL(12,2) NOT NULL,
            descripcion TEXT,
            imagen MEDIUMBLOB NULL,
            imagen_tipo VARCHAR(20) DEFAULT 'none',
            imagen_mime VARCHAR(80) NULL,
            imagen_nombre VARCHAR(255) NULL
          )
          """
        )
        cursor.execute('SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s', ('producto', 'descripcion'))
        if cursor.fetchone()[0] == 0:
          cursor.execute('ALTER TABLE producto ADD COLUMN descripcion TEXT')
        cursor.execute('SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s', ('producto', 'imagen'))
        if cursor.fetchone()[0] == 0:
          cursor.execute('ALTER TABLE producto ADD COLUMN imagen MEDIUMBLOB')
        cursor.execute('SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s', ('producto', 'imagen_tipo'))
        if cursor.fetchone()[0] == 0:
          cursor.execute('ALTER TABLE producto ADD COLUMN imagen_tipo VARCHAR(20) DEFAULT "none"')
        cursor.execute('SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s', ('producto', 'imagen_mime'))
        if cursor.fetchone()[0] == 0:
          cursor.execute('ALTER TABLE producto ADD COLUMN imagen_mime VARCHAR(80)')
        cursor.execute('SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s', ('producto', 'imagen_nombre'))
        if cursor.fetchone()[0] == 0:
          cursor.execute('ALTER TABLE producto ADD COLUMN imagen_nombre VARCHAR(255)')
      connection.commit()
    finally:
      connection.close()

  def leer_productos():
    connection = get_mysql_connection()
    try:
      with connection.cursor(dictionary=True) as cursor:
        cursor.execute('SELECT * FROM producto ORDER BY idproducto')
        return cursor.fetchall()
    finally:
      connection.close()

  def insertar_producto(connection, datos):
    with connection.cursor() as cursor:
      cursor.execute(
        'INSERT INTO producto (producto, marca, precio, descripcion, imagen, imagen_tipo, imagen_mime, imagen_nombre) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
        (
          datos['producto'],
          datos['marca'],
          datos['precio'],
          datos.get('descripcion'),
          datos.get('imagen'),
          datos.get('imagen_tipo', 'none'),
          datos.get('imagen_mime'),
          datos.get('imagen_nombre'),
        ),
      )
      return cursor.lastrowid

  def actualizar_producto(connection, identificador, datos):
    with connection.cursor() as cursor:
      cursor.execute('SELECT idproducto FROM producto WHERE idproducto=%s FOR UPDATE', (identificador,))
      if cursor.fetchone() is None:
        raise ValueError('El producto ya no existe. Recarga la tabla.')
      cursor.execute(
        'UPDATE producto SET producto=%s, marca=%s, precio=%s, descripcion=%s, imagen=%s, imagen_tipo=%s, imagen_mime=%s, imagen_nombre=%s WHERE idproducto=%s',
        (
          datos['producto'],
          datos['marca'],
          datos['precio'],
          datos.get('descripcion'),
          datos.get('imagen'),
          datos.get('imagen_tipo', 'none'),
          datos.get('imagen_mime'),
          datos.get('imagen_nombre'),
          identificador,
        ),
      )

  def eliminar_producto(connection, identificador):
    with connection.cursor() as cursor:
      cursor.execute('DELETE FROM producto WHERE idproducto=%s', (identificador,))
      if cursor.rowcount != 1:
        raise ValueError('El producto ya no existe. Recarga la tabla.')

  def obtener_producto_por_id(identificador):
    connection = get_mysql_connection()
    try:
      with connection.cursor(dictionary=True) as cursor:
        cursor.execute('SELECT * FROM producto WHERE idproducto=%s', (identificador,))
        return cursor.fetchone()
    finally:
      connection.close()
