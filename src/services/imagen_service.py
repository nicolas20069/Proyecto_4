import base64
import io
import ipaddress
import mimetypes
import os
import socket
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import requests
from cryptography.fernet import Fernet
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

from src.config.mongo_connection import get_mongo_connection

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_URL_BYTES = 10 * 1024 * 1024
ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
IMAGES_ROOT = Path(__file__).resolve().parents[2] / 'images'
IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
(IMAGES_ROOT / 'original').mkdir(parents=True, exist_ok=True)
(IMAGES_ROOT / 'comprimidas').mkdir(parents=True, exist_ok=True)


def _image_key_material():
    raw = os.getenv('IMAGE_ENCRYPTION_KEY') or 'Proyecto4-Local-Images-Key-32B!'
    encoded = raw.encode('utf-8')
    if len(encoded) < 32:
        encoded = (encoded + b'0' * 32)[:32]
    return base64.urlsafe_b64encode(encoded[:32])


def _get_fernet():
    return Fernet(_image_key_material())


def _hostname_is_private(hostname):
    if not hostname:
        return True
    hostname = hostname.lower().strip()
    if hostname in {'localhost', '127.0.0.1', '::1', '0.0.0.0'}:
        return True
    try:
        return ipaddress.ip_address(hostname).is_private or ipaddress.ip_address(hostname).is_loopback or ipaddress.ip_address(hostname).is_link_local or ipaddress.ip_address(hostname).is_reserved
    except ValueError:
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            return True
        for family, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            try:
                parsed = ipaddress.ip_address(ip)
                if parsed.is_private or parsed.is_loopback or parsed.is_link_local or parsed.is_reserved:
                    return True
            except ValueError:
                continue
        return False


def _safe_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'}:
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    return not _hostname_is_private(hostname)


def _ensure_valid_filename(filename):
    safe_name = secure_filename(filename or 'imagen')
    if not safe_name:
        safe_name = f'imagen-{uuid4().hex}'
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError('Tipo de imagen no permitido. Usa JPG, PNG, WEBP o GIF.')
    return safe_name


def _detect_mime_from_bytes(data):
    if not data:
        raise ValueError('No se recibió contenido para la imagen.')
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            detected = img.format
            mime = Image.MIME.get(detected, None)
            if mime not in ALLOWED_MIME_TYPES:
                raise ValueError('El archivo no es una imagen válida.')
            return mime
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError('El archivo no es una imagen válida o está corrupto.')


def _compress_image(data):
    image = Image.open(io.BytesIO(data))
    image = image.convert('RGB')
    max_width = 1600
    max_height = 1600
    if image.width > max_width or image.height > max_height:
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=78, optimize=True)
    return buffer.getvalue()


def guardar_archivo_local_encriptado(data, filename, categoria='original', is_compressed=False):
    if not data:
        raise ValueError('No se recibió contenido para guardar la imagen.')
    target_dir = IMAGES_ROOT / ('comprimidas' if is_compressed or categoria == 'comprimidas' else categoria)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = secure_filename(filename or 'imagen')
    if not safe_name:
        safe_name = f'imagen-{uuid4().hex}.png'
    stem = Path(safe_name).stem or 'imagen'
    target_name = f'{stem}.enc'
    encrypted = _get_fernet().encrypt(data)
    target_path = target_dir / target_name
    with open(target_path, 'wb') as archivo:
        archivo.write(encrypted)
    return {
        'ruta': str(target_path),
        'nombre': target_name,
        'categoria': target_dir.name,
        'encriptado': True,
        'is_compressed': bool(is_compressed),
    }


def leer_archivo_local_encriptado(path):
    with open(path, 'rb') as archivo:
        return _get_fernet().decrypt(archivo.read())


def _validate_and_prepare_bytes(data, filename, source):
    if not data:
        raise ValueError('No se recibió una imagen válida.')
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError('La imagen supera el límite permitido de 10 MB.')
    safe_name = _ensure_valid_filename(filename)
    mime = _detect_mime_from_bytes(data)
    return {
        'nombre': safe_name,
        'mimetype': mime,
        'bytes': data,
        'tamano': len(data),
        'fuente': source,
    }


def obtener_imagen_desde_url(url):
    if not _safe_url(url):
        raise ValueError('La URL de la imagen no es segura o no es accesible.')
    try:
        response = requests.get(url, timeout=10, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
        if response.status_code != 200:
            raise ValueError('La URL de la imagen no responde correctamente.')
        final_url = response.url
        if not _safe_url(final_url):
            raise ValueError('La URL final de la imagen no es segura.')
        content_type = response.headers.get('Content-Type', '').split(';')[0].lower()
        if content_type not in ALLOWED_MIME_TYPES:
            raise ValueError('La URL no apunta a una imagen válida.')
        data = response.content
        if len(data) > MAX_URL_BYTES:
            raise ValueError('La imagen descargada supera el límite permitido.')
        prepared = _validate_and_prepare_bytes(data, Path(urlparse(url).path).name or 'imagen', 'url')
        prepared['url_original'] = url
        return prepared
    except requests.RequestException as exc:
        raise ValueError('No fue posible descargar la URL de la imagen.') from exc


def procesar_imagen_entrada(formulario, archivos):
    uploaded_file = archivos.get('imagen') if archivos else None
    if uploaded_file and getattr(uploaded_file, 'filename', ''):
        data = uploaded_file.read()
        prepared = _validate_and_prepare_bytes(data, uploaded_file.filename, 'archivo')
        return prepared
    url = (formulario or {}).get('url', '').strip()
    if url:
        return obtener_imagen_desde_url(url)
    return None


def clasificar_y_guardar_imagen(product_id, datos_producto, imagen_bytes, mime_type, source):
    if not imagen_bytes:
        raise ValueError('No se recibió una imagen válida.')
    if len(imagen_bytes) > MAX_IMAGE_BYTES:
        raise ValueError('La imagen supera el límite permitido de 10 MB.')
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError('Tipo de imagen no permitido. Usa JPG, PNG, WEBP o GIF.')
    try:
        _detect_mime_from_bytes(imagen_bytes)
    except ValueError:
        raise

    db = get_mongo_connection()
    fs = db.fs
    if len(imagen_bytes) <= 1024 * 1024:
        return {
            'kind': 'mysql',
            'data': imagen_bytes,
            'mime': mime_type,
            'metadata': None,
        }

    original_id = fs.files.insert_one({
        'producto_id': product_id,
        'tipo_archivo': 'original',
        'mimetype': mime_type,
        'tamanio': len(imagen_bytes),
        'source': source,
    }).inserted_id
    fs.chunks.insert_one({'files_id': original_id, 'n': 0, 'data': imagen_bytes})

    original_local = guardar_archivo_local_encriptado(imagen_bytes, f'{product_id}_{datos_producto.get("producto", "producto")}.png', 'original')
    metadata = {
        'producto_id': product_id,
        'producto': datos_producto.get('producto'),
        'marca': datos_producto.get('marca'),
        'precio': str(datos_producto.get('precio', '0')),
        'descripcion': datos_producto.get('descripcion', ''),
        'url': f'/imagen/mongo/{original_id}',
        'tamano_imagen': len(imagen_bytes),
        'tamano_imagen_comprimida': None,
        'compressed_file_id': None,
        'tipo': 'original',
        'mime_type': mime_type,
        'ruta_local_encriptada': original_local['ruta'],
        'categoria_local': original_local['categoria'],
        'original_file_id': str(original_id),
        'url_original': None,
    }

    if len(imagen_bytes) > 3 * 1024 * 1024:
        compressed = _compress_image(imagen_bytes)
        compressed_id = fs.files.insert_one({
            'producto_id': product_id,
            'tipo_archivo': 'compressed',
            'mimetype': 'image/jpeg',
            'tamanio': len(compressed),
            'source': source,
        }).inserted_id
        fs.chunks.insert_one({'files_id': compressed_id, 'n': 0, 'data': compressed})
        compressed_local = guardar_archivo_local_encriptado(compressed, f'{product_id}_{datos_producto.get("producto", "producto")}_compressed.jpg', 'comprimidas', is_compressed=True)
        metadata['url'] = f'/imagen/mongo/{compressed_id}'
        metadata['tamano_imagen_comprimida'] = len(compressed)
        metadata['compressed_file_id'] = str(compressed_id)
        metadata['tipo'] = 'compressed'
        metadata['url_original'] = f'/imagen/original/{original_id}'
        metadata['compressed_mimetype'] = 'image/jpeg'
        metadata['ruta_local_encriptada_comprimida'] = compressed_local['ruta']
        metadata['categoria_local_comprimida'] = compressed_local['categoria']

    db.producto.insert_one(metadata)
    return {
        'kind': 'mongo_original' if metadata.get('tamano_imagen_comprimida') is None else 'mongo_compressed',
        'metadata': metadata,
        'mongo_original_id': original_id,
        'mongo_compressed_id': metadata.get('compressed_file_id'),
        'mime': mime_type,
        'data': None,
    }
