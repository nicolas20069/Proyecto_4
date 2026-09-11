import io
import os
import unittest
from uuid import uuid4

from PIL import Image

from app import app
from src.config.mysql_connection import get_mysql_connection
from src.config.mongo_connection import get_mongo_connection
from src.services.imagen_service import clasificar_y_guardar_imagen, guardar_archivo_local_encriptado, obtener_imagen_desde_url


class Proyecto4AuthCRUDTests(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.username = f'user_{uuid4().hex[:8]}'
        self.password = 'Secret123!'

    def tearDown(self):
        mongo = get_mongo_connection().producto
        mongo.delete_many({'producto': {'$regex': '^__test_'}})
        connection = get_mysql_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM usuario WHERE usuario LIKE %s', ('user_%',))
                cursor.execute('DELETE FROM producto WHERE producto LIKE %s', ('__test_%',))
            connection.commit()
        finally:
            connection.close()

    def test_register_and_login_and_logout(self):
        response = self.client.post('/register', data={
            'usuario': self.username,
            'password': self.password,
            'confirmar_password': self.password,
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'login', response.data.lower())

        response = self.client.post('/login', data={
            'usuario': self.username,
            'password': self.password,
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'productos', response.data.lower())

        with self.client.session_transaction() as sesion:
            csrf = sesion['csrf_token']
        response = self.client.post('/productos/guardar', data={
            'producto': '__test_logout',
            'marca': 'Marca',
            'precio': '10.00',
            'descripcion': 'x',
            'csrf_token': csrf,
        }, follow_redirects=True)
        self.assertIn(b'Producto guardado', response.data)

        response = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'login', response.data.lower())

    def test_product_routes_require_login(self):
        response = self.client.get('/productos')
        self.assertIn(response.status_code, (302, 401))

    def test_create_product_with_local_file(self):
        self.client.post('/register', data={
            'usuario': self.username,
            'password': self.password,
            'confirmar_password': self.password,
        }, follow_redirects=True)
        self.client.post('/login', data={
            'usuario': self.username,
            'password': self.password,
        }, follow_redirects=True)

        image = Image.new('RGB', (100, 100), color='blue')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)

        with self.client.session_transaction() as sesion:
            csrf = sesion['csrf_token']

        data = {
            'producto': '__test_producto_local',
            'marca': 'Test',
            'precio': '25.50',
            'descripcion': 'Producto local',
            'csrf_token': csrf,
            'imagen': (buffer, 'foto.png'),
        }
        response = self.client.post('/productos/guardar', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Producto guardado', response.data)

    def test_store_images_by_size_class(self):
        self.client.post('/register', data={
            'usuario': self.username,
            'password': self.password,
            'confirmar_password': self.password,
        }, follow_redirects=True)
        self.client.post('/login', data={
            'usuario': self.username,
            'password': self.password,
        }, follow_redirects=True)

        with self.client.session_transaction() as sesion:
            csrf = sesion['csrf_token']

        for nombre, size_bytes in [
            ('__test_small', 700 * 1024),
            ('__test_medium', 2 * 1024 * 1024),
            ('__test_large', 4 * 1024 * 1024),
        ]:
            image = Image.new('RGB', (1200, 1200), color='green')
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            payload = buffer.getvalue()
            if len(payload) < size_bytes:
                chunk = b'\x00' * (size_bytes - len(payload))
                payload += chunk
            data = {
                'producto': nombre,
                'marca': 'Test',
                'precio': '15.00',
                'descripcion': 'imagen por tamaño',
                'csrf_token': csrf,
                'imagen': (io.BytesIO(payload), f'{nombre}.png'),
            }
            response = self.client.post('/productos/guardar', data=data, content_type='multipart/form-data', follow_redirects=True)
            self.assertIn(b'Producto guardado', response.data)

        mongo = get_mongo_connection().producto
        small = mongo.find_one({'producto': '__test_small'})
        medium = mongo.find_one({'producto': '__test_medium'})
        large = mongo.find_one({'producto': '__test_large'})
        self.assertIsNone(small)
        self.assertIsNotNone(medium)
        self.assertIsNotNone(large)
        self.assertIsNotNone(medium.get('original_file_id'))
        self.assertIsNone(medium.get('compressed_file_id'))
        self.assertIsNotNone(large.get('compressed_file_id'))
        self.assertEqual(medium.get('url'), f'/imagen/mongo/{medium.get("original_file_id")}')
        self.assertEqual(large.get('url'), f'/imagen/mongo/{large.get("compressed_file_id")}')
        self.assertGreaterEqual(medium.get('tamano_imagen', 0), 2 * 1024 * 1024)
        self.assertIsNotNone(large.get('tamano_imagen_comprimida'))

    def test_medium_images_keep_compressed_fields_null(self):
        image = Image.new('RGB', (2000, 2000), color='orange')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        payload = buffer.getvalue() + b'\x00' * (2 * 1024 * 1024)
        payload = payload[:2 * 1024 * 1024]
        result = clasificar_y_guardar_imagen(
            200004,
            {'producto': '__test_medium_regression', 'marca': 'X', 'precio': '1', 'descripcion': 'x'},
            payload,
            'image/png',
            'archivo',
        )
        self.assertEqual(result['kind'], 'mongo_original')
        self.assertIsNone(result['metadata'].get('tamano_imagen_comprimida'))
        self.assertIsNone(result['metadata'].get('compressed_file_id'))
        self.assertIsNone(result['metadata'].get('url_original'))

    def test_gridfs_large_image_storage_is_valid(self):
        image = Image.new('RGB', (2000, 2000), color='purple')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        payload = buffer.getvalue() + b'\x00' * (4 * 1024 * 1024)

        result = clasificar_y_guardar_imagen(
            999999,
            {'producto': '__test_gridfs', 'marca': 'GridFS', 'precio': '99.99', 'descripcion': 'gridfs'},
            payload,
            'image/png',
            'archivo',
        )

        self.assertEqual(result['kind'], 'mongo_compressed')
        self.assertIn('original_file_id', result['metadata'])
        self.assertIn('compressed_file_id', result['metadata'])
        self.assertEqual(result['metadata']['url'], f"/imagen/mongo/{result['metadata']['compressed_file_id']}")
        fs = get_mongo_connection().fs
        self.assertTrue(fs.files.find_one({'_id': __import__('bson').objectid.ObjectId(result['metadata']['original_file_id'])}) is not None)
        self.assertTrue(fs.chunks.find_one({'files_id': __import__('bson').objectid.ObjectId(result['metadata']['original_file_id'])}) is not None)

    def test_invalid_uploads_and_private_urls_are_rejected(self):
        self.client.post('/register', data={
            'usuario': self.username,
            'password': self.password,
            'confirmar_password': self.password,
        }, follow_redirects=True)
        self.client.post('/login', data={
            'usuario': self.username,
            'password': self.password,
        }, follow_redirects=True)

        with self.client.session_transaction() as sesion:
            csrf = sesion['csrf_token']

        invalid_response = self.client.post('/productos/guardar', data={
            'producto': '__test_invalid_file',
            'marca': 'Marca',
            'precio': '10.00',
            'descripcion': 'x',
            'csrf_token': csrf,
            'imagen': (io.BytesIO(b'not-a-real-image'), 'fake.txt'),
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'tipo de imagen', invalid_response.data.lower())

        image = Image.new('RGB', (100, 100), color='red')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        payload = buffer.getvalue() + b'\x00' * (11 * 1024 * 1024)
        large_response = self.client.post('/productos/guardar', data={
            'producto': '__test_large_rejected',
            'marca': 'Marca',
            'precio': '12.00',
            'descripcion': 'x',
            'csrf_token': csrf,
            'imagen': (io.BytesIO(payload), 'large.png'),
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'10 mb', large_response.data.lower())

        with self.assertRaises(ValueError):
            obtener_imagen_desde_url('http://127.0.0.1:5000/imagen.png')

    def test_storage_thresholds_follow_expected_classification(self):
        def png_payload(size_bytes):
            image = Image.new('RGB', (200, 200), color='orange')
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            payload = buffer.getvalue()
            if len(payload) < size_bytes:
                payload += b'\x00' * (size_bytes - len(payload))
            return payload[:size_bytes]

        small = clasificar_y_guardar_imagen(
            200001,
            {'producto': '__test_small_direct', 'marca': 'X', 'precio': '1', 'descripcion': 'x'},
            png_payload(500 * 1024),
            'image/png',
            'archivo',
        )
        self.assertEqual(small['kind'], 'mysql')
        self.assertIsNone(small['metadata'])

        medium = clasificar_y_guardar_imagen(
            200002,
            {'producto': '__test_medium_direct', 'marca': 'X', 'precio': '1', 'descripcion': 'x'},
            png_payload(2 * 1024 * 1024),
            'image/png',
            'archivo',
        )
        self.assertEqual(medium['kind'], 'mongo_original')
        self.assertIn('original_file_id', medium['metadata'])
        self.assertIsNone(medium['metadata'].get('compressed_file_id'))
        self.assertIsNone(medium['metadata'].get('tamano_imagen_comprimida'))
        self.assertEqual(medium['metadata']['url'], f"/imagen/mongo/{medium['metadata']['original_file_id']}")

        large = clasificar_y_guardar_imagen(
            200003,
            {'producto': '__test_large_direct', 'marca': 'X', 'precio': '1', 'descripcion': 'x'},
            png_payload(5 * 1024 * 1024),
            'image/png',
            'archivo',
        )
        self.assertEqual(large['kind'], 'mongo_compressed')
        self.assertIn('original_file_id', large['metadata'])
        self.assertIn('compressed_file_id', large['metadata'])
        self.assertIsNotNone(large['metadata'].get('tamano_imagen_comprimida'))
        self.assertEqual(large['metadata']['url'], f"/imagen/mongo/{large['metadata']['compressed_file_id']}")

    def test_encrypted_local_storage_and_compressed_folder(self):
        image = Image.new('RGB', (400, 400), color='purple')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        payload = buffer.getvalue() + b'\x00' * (4 * 1024 * 1024)

        original = guardar_archivo_local_encriptado(payload, 'imagen_grande.png', 'original')
        compressed = guardar_archivo_local_encriptado(payload, 'imagen_grande.png', 'comprimidas', is_compressed=True)

        self.assertTrue(original['encriptado'])
        self.assertTrue(compressed['encriptado'])
        self.assertIn('original', original['ruta'])
        self.assertIn('comprimidas', compressed['ruta'])
        self.assertTrue(original['ruta'].endswith('.enc'))
        self.assertTrue(compressed['ruta'].endswith('.enc'))
        self.assertNotEqual(open(original['ruta'], 'rb').read(), payload)


if __name__ == '__main__':
    unittest.main()
