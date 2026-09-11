from decimal import Decimal, InvalidOperation
from functools import wraps
from secrets import token_hex
from urllib.parse import urlparse

from bson import ObjectId
from flask import Blueprint, current_app, flash, redirect, render_template, request, Response, session, url_for
from gridfs import GridFS
from pymongo.errors import PyMongoError

from src.config.mongo_connection import get_mongo_connection
from src.config.mysql_connection import get_mysql_connection
from src.models.model_productos import Producto
from src.models.model_usuarios import Usuario
from src.services.imagen_service import procesar_imagen_entrada

productos_c = Blueprint('productos_c', __name__, template_folder='../templates')


def login_required(view_func):
    @wraps(view_func)
    def decorated(*args, **kwargs):
        if not session.get('usuario_id'):
            flash('Debes iniciar sesión para acceder.', 'warning')
            return redirect(url_for('productos_c.login'))
        return view_func(*args, **kwargs)
    return decorated


def csrf_required(view_func):
    @wraps(view_func)
    def decorated(*args, **kwargs):
        token_actual = session.get('csrf_token')
        token_enviado = request.form.get('csrf_token', '')
        if not token_actual or token_actual != token_enviado:
            flash('La sesión expiró o el formulario es inválido.', 'danger')
            return redirect(url_for('productos_c.obtener_productos'))
        return view_func(*args, **kwargs)
    return decorated


def asegurar_csrf():
    session.setdefault('csrf_token', token_hex(32))


def _mongo_metadata_por_producto(producto_id):
    db = get_mongo_connection()
    return db.producto.find_one({'producto_id': producto_id})


def _eliminar_mongo_producto(producto_id):
    db = get_mongo_connection()
    metadata = list(db.producto.find({'$or': [{'producto_id': producto_id}, {'idproducto': producto_id}]}))
    for doc in metadata:
        for key in ('original_file_id', 'compressed_file_id'):
            file_id = doc.get(key)
            if not file_id:
                continue
            try:
                db.fs.files.delete_one({'_id': ObjectId(file_id)})
                db.fs.chunks.delete_many({'files_id': ObjectId(file_id)})
            except Exception:
                pass
        db.producto.delete_one({'_id': doc['_id']})


def _crear_mongo_metadata(producto_id, datos, prepared):
    db = get_mongo_connection()
    fs = GridFS(db)
    payload = prepared['bytes']
    original_id = fs.put(payload, filename=prepared['nombre'], contentType=prepared['mimetype'], producto_id=producto_id, tipo='original', mime_type=prepared['mimetype'])
    metadata = {
        'idproducto': producto_id,
        'producto_id': producto_id,
        'producto': datos['producto'],
        'marca': datos['marca'],
        'precio': str(datos['precio']),
        'descripcion': datos.get('descripcion', ''),
        'url': f'/imagen/mongo/{original_id}',
        'tamano_imagen': len(payload),
        'tamano_imagen_comprimida': None,
        'compressed_file_id': None,
        'tipo': 'original',
        'mime_type': prepared['mimetype'],
        'original_file_id': str(original_id),
        'url_original': None,
    }
    if len(payload) > 3 * 1024 * 1024:
        from src.services.imagen_service import _compress_image
        compressed = _compress_image(payload)
        compressed_id = fs.put(compressed, filename=f'compressed_{prepared["nombre"]}', contentType='image/jpeg', producto_id=producto_id, tipo='compressed', mime_type='image/jpeg')
        metadata['url'] = f'/imagen/mongo/{compressed_id}'
        metadata['tamano_imagen_comprimida'] = len(compressed)
        metadata['compressed_file_id'] = str(compressed_id)
        metadata['tipo'] = 'compressed'
        metadata['url_original'] = f'/imagen/original/{original_id}'
        metadata['compressed_mimetype'] = 'image/jpeg'
    db.producto.insert_one(metadata)
    return metadata


def unir_productos():
    productos = Producto.leer_productos()
    mongo_docs = list(get_mongo_connection().producto.find({}))
    docs_por_producto = {}
    for doc in mongo_docs:
        docs_por_producto[doc.get('producto_id')] = doc
    filas = []
    for producto in productos:
        doc = docs_por_producto.get(producto['idproducto'])
        url = (doc or {}).get('url', '')
        url_original = (doc or {}).get('url_original', '') or (doc or {}).get('original_file_id') and f'/imagen/original/{(doc or {}).get("original_file_id")}'
        if not url and producto.get('imagen'):
            url = f'/imagen/mysql/{producto["idproducto"]}'
        filas.append({
            'idproducto': producto['idproducto'],
            'producto': producto['producto'],
            'marca': producto['marca'],
            'precio': producto['precio'],
            'descripcion': producto.get('descripcion', ''),
            'url': url,
            'url_original': url_original,
            'origen': 'MySQL + MongoDB' if doc else 'Solo MySQL',
            'clave': f'sql-{producto["idproducto"]}',
            'documento': doc,
            'imagen_tipo': producto.get('imagen_tipo', 'none'),
            'imagen_mime': producto.get('imagen_mime'),
            'imagen_nombre': producto.get('imagen_nombre'),
        })
    return filas


@productos_c.route('/')
@productos_c.route('/Productos')
@productos_c.route('/productos')
@login_required
def obtener_productos():
    asegurar_csrf()
    try:
        return render_template('productos.html', data=unir_productos(), csrf_token=session['csrf_token'])
    except Exception:
        current_app.logger.exception('No se pudieron consultar las bases de datos')
        flash('No se pudo cargar la tabla. Revisa las conexiones y la relación de los datos.', 'danger')
        return render_template('productos.html', data=[], error_carga=True), 503


@productos_c.route('/imagenes_productos')
@login_required
def obtener_imagenes():
    return obtener_productos()


@productos_c.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    usuario = (request.form.get('usuario') or '').strip()
    password = request.form.get('password', '')
    confirmar = request.form.get('confirmar_password', '')
    if not usuario or len(usuario) < 3:
        flash('El usuario es obligatorio y debe tener al menos 3 caracteres.', 'warning')
        return redirect(url_for('productos_c.register'))
    if len(password) < 6:
        flash('La contraseña debe tener al menos 6 caracteres.', 'warning')
        return redirect(url_for('productos_c.register'))
    if password != confirmar:
        flash('La confirmación de contraseña no coincide.', 'warning')
        return redirect(url_for('productos_c.register'))
    try:
        Usuario.registrar(usuario, password)
        flash('Usuario registrado correctamente.', 'success')
        return redirect(url_for('productos_c.login'))
    except ValueError as exc:
        flash(str(exc), 'warning')
        return redirect(url_for('productos_c.register'))


@productos_c.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    usuario = (request.form.get('usuario') or '').strip()
    password = request.form.get('password', '')
    user = Usuario.autenticar(usuario, password)
    if not user:
        flash('Credenciales inválidas. Verifica tus datos.', 'warning')
        return redirect(url_for('productos_c.login'))
    session.clear()
    session['usuario_id'] = user['idusuario']
    session['usuario'] = user['usuario']
    asegurar_csrf()
    flash('Sesión iniciada correctamente.', 'success')
    return redirect(url_for('productos_c.obtener_productos'))


@productos_c.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('productos_c.login'))


def validar_datos(formulario):
    datos = {campo: formulario.get(campo, '').strip() for campo in ('producto', 'marca', 'precio', 'descripcion')}
    if not datos['producto'] or not datos['marca']:
        raise ValueError('Producto y marca son obligatorios.')
    if len(datos['producto']) > 200 or len(datos['marca']) > 200 or len(datos.get('descripcion', '')) > 2000:
        raise ValueError('Uno de los campos supera la longitud permitida.')
    try:
        precio = Decimal(datos['precio'])
        if not precio.is_finite() or precio < 0 or precio > Decimal('9999999999.99') or precio != precio.quantize(Decimal('0.01')):
            raise ValueError()
    except (InvalidOperation, ValueError):
        raise ValueError('El precio debe ser un número positivo o cero, con máximo dos decimales; no se permite texto.')
    datos['precio'] = precio
    return datos


@productos_c.route('/productos/guardar', methods=['POST'])
@login_required
@csrf_required
def guardar_producto():
    try:
        datos = validar_datos(request.form)
        producto_id = request.form.get('idproducto')
        archivo = request.files.get('imagen')
        if archivo and archivo.filename:
            prepared = procesar_imagen_entrada(request.form, request.files)
        else:
            prepared = procesar_imagen_entrada(request.form, request.files)
        connection = get_mysql_connection()
        try:
            connection.start_transaction()
            if producto_id:
                producto_actual = Producto.obtener_producto_por_id(producto_id)
                if producto_actual is None:
                    raise ValueError('El producto ya no existe.')
                if prepared is None:
                    datos['imagen'] = producto_actual.get('imagen')
                    datos['imagen_tipo'] = producto_actual.get('imagen_tipo', 'none')
                    datos['imagen_mime'] = producto_actual.get('imagen_mime')
                    datos['imagen_nombre'] = producto_actual.get('imagen_nombre')
                else:
                    if prepared['tamano'] <= 1024 * 1024:
                        datos['imagen'] = prepared['bytes']
                        datos['imagen_tipo'] = 'mysql_blob'
                        datos['imagen_mime'] = prepared['mimetype']
                        datos['imagen_nombre'] = prepared['nombre']
                        _eliminar_mongo_producto(int(producto_id))
                    else:
                        datos['imagen'] = None
                        datos['imagen_tipo'] = 'mongo_compressed'
                        datos['imagen_mime'] = prepared['mimetype']
                        datos['imagen_nombre'] = prepared['nombre']
                        _eliminar_mongo_producto(int(producto_id))
                        _crear_mongo_metadata(int(producto_id), datos, prepared)
                Producto.actualizar_producto(connection, int(producto_id), datos)
            else:
                if prepared is None:
                    datos['imagen'] = None
                    datos['imagen_tipo'] = 'none'
                    datos['imagen_mime'] = None
                    datos['imagen_nombre'] = None
                elif prepared['tamano'] <= 1024 * 1024:
                    datos['imagen'] = prepared['bytes']
                    datos['imagen_tipo'] = 'mysql_blob'
                    datos['imagen_mime'] = prepared['mimetype']
                    datos['imagen_nombre'] = prepared['nombre']
                else:
                    datos['imagen'] = None
                    datos['imagen_tipo'] = 'mongo_compressed'
                    datos['imagen_mime'] = prepared['mimetype']
                    datos['imagen_nombre'] = prepared['nombre']
                producto_id = Producto.insertar_producto(connection, datos)
                if prepared and prepared['tamano'] > 1024 * 1024:
                    _crear_mongo_metadata(int(producto_id), datos, prepared)
            connection.commit()
        finally:
            connection.close()
        flash('Producto guardado correctamente.', 'success')
    except ValueError as exc:
        flash(str(exc), 'warning')
    except (PyMongoError, Exception) as exc:
        current_app.logger.exception('No se pudo guardar el producto')
        flash('No se pudo completar el guardado del producto. Revisa la imagen y las conexiones.', 'danger')
    return redirect(url_for('productos_c.obtener_productos'))


@productos_c.route('/productos/eliminar', methods=['POST'])
@login_required
@csrf_required
def eliminar_producto():
    try:
        idproducto = request.form.get('idproducto')
        if not idproducto:
            clave = request.form.get('clave', '')
            if clave.startswith('sql-'):
                idproducto = clave.split('-', 1)[1]
        if not idproducto:
            raise ValueError('Selecciona un producto válido para eliminar.')
        connection = get_mysql_connection()
        try:
            connection.start_transaction()
            producto = Producto.obtener_producto_por_id(idproducto)
            if producto is None:
                raise ValueError('El producto ya no existe.')
            _eliminar_mongo_producto(int(idproducto))
            Producto.eliminar_producto(connection, int(idproducto))
            connection.commit()
        finally:
            connection.close()
        flash('Producto eliminado correctamente.', 'success')
    except ValueError as exc:
        flash(str(exc), 'warning')
    except Exception:
        current_app.logger.exception('No se pudo eliminar el producto')
        flash('No se pudo eliminar el producto.', 'danger')
    return redirect(url_for('productos_c.obtener_productos'))


@productos_c.route('/imagen/mysql/<int:idproducto>')
@login_required
def servir_imagen_mysql(idproducto):
    producto = Producto.obtener_producto_por_id(idproducto)
    if not producto or not producto.get('imagen'):
        return redirect(url_for('productos_c.obtener_productos'))
    return Response(producto['imagen'], mimetype=producto.get('imagen_mime') or 'image/jpeg')


@productos_c.route('/imagen/mongo/<string:archivo_id>')
@login_required
def servir_imagen_mongo(archivo_id):
    fs = GridFS(get_mongo_connection())
    try:
        archivo = fs.get(ObjectId(archivo_id))
    except Exception:
        return redirect(url_for('productos_c.obtener_productos'))
    return Response(archivo.read(), mimetype=archivo.content_type or 'image/jpeg')


@productos_c.route('/imagen/original/<string:archivo_id>')
@login_required
def servir_imagen_original(archivo_id):
    return servir_imagen_mongo(archivo_id)


@productos_c.route('/productos/<int:idproducto>')
@login_required
def detalle_producto(idproducto):
    producto = Producto.obtener_producto_por_id(idproducto)
    if not producto:
        flash('El producto solicitado no existe.', 'warning')
        return redirect(url_for('productos_c.obtener_productos'))
    documento = _mongo_metadata_por_producto(idproducto)
    return render_template('detalle_producto.html', producto=producto, documento=documento)
