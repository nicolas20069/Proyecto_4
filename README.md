# Proyecto 4 — CRUD con autenticación, validación de imágenes y almacenamiento seguro

## Descripción
Este proyecto es una aplicación Flask para gestionar productos con autenticación, validación de entradas, manejo de imágenes y almacenamiento diferenciado entre MySQL y MongoDB/GridFS. El sistema cumple con la regla solicitada de guardar un archivo local cifrado bajo una estructura protegida por sesión y además usar GridFS para el almacenamiento de imágenes grandes.

## Objetivo general
- Registrar usuarios y autenticarlos con credenciales seguras.
- Crear, consultar, actualizar y eliminar productos.
- Validar campos del formulario y archivos de imagen.
- Guardar imágenes según su tamaño real:
  - <= 1 MB -> MySQL BLOB
  - > 1 MB y <= 3 MB -> MongoDB GridFS original
  - > 3 MB -> MongoDB GridFS original + comprimida
- Cifrar los archivos locales almacenados en la carpeta images.
- Mantener los archivos de imagen ocultos o no visibles en el explorador si el usuario no ha iniciado sesión.
- Dejar una batería de pruebas verificable del comportamiento solicitado.

## Tecnologías utilizadas
- Python 3.12
- Flask
- MySQL Connector
- PyMongo
- MongoDB GridFS
- Pillow
- python-dotenv
- cryptography
- requests
- Jinja2
- Bootstrap

## Estructura principal
- app.py: aplicación principal y configuración general.
- src/controllers/controller.py: rutas, validación, control de acceso y manejo de imágenes.
- src/models/model_productos.py: acceso a MySQL para productos.
- src/models/model_usuarios.py: acceso a MySQL para usuarios.
- src/services/imagen_service.py: validación, compresión, cifrado local y clasificación.
- src/config/mysql_connection.py: conexión a MySQL.
- src/config/mongo_connection.py: conexión a MongoDB.
- src/templates/: plantillas HTML.
- tests/test_app.py: pruebas de autenticación, CRUD y validaciones de imágenes.
- images/: almacenamiento local cifrado de imágenes originales y comprimidas.

## Requisitos previos
Debes tener instalados:
- Python 3.10 o superior
- MySQL en ejecución
- MongoDB en ejecución
- acceso a la carpeta del proyecto

## Instalación
Desde la terminal PowerShell, dentro de la carpeta del proyecto:

```powershell
python -m venv env
.\env\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Configuración de entorno
Crea un archivo `.env` en la raíz del proyecto con variables como estas:

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=tu_password
MYSQL_DATABASE=mercancia
MONGO_URI=mongodb://localhost:27017/
MONGO_DATABASE=mercancia
SECRET_KEY=cambia_esta_clave_por_una_segura
FLASK_ENV=development
IMAGE_ENCRYPTION_KEY=Proyecto4-Local-Images-Key-32B!
```

Importante:
- La clave `IMAGE_ENCRYPTION_KEY` se usa para cifrar los archivos locales guardados en la carpeta images.
- Si no se define, el proyecto usa una clave por defecto con formato seguro, aunque lo recomendable es definir una propia.

## Bases de datos
### MySQL
Se usa para:
- usuarios
- productos
- almacenamiento de imágenes pequeñas en BLOB

### MongoDB
Se usa para:
- metadatos del producto
- GridFS para imágenes grandes
- archivos originales y comprimidos

## Regla de almacenamiento de imágenes
```text
<= 1 MB  -> MySQL BLOB
> 1 MB y <= 3 MB -> GridFS original
> 3 MB -> GridFS original + comprimida
```

### Almacenamiento local cifrado
La carpeta `images` contiene una estructura protegida:

```text
images/
├── original/
│   └── nombre_archivo.enc
├── comprimidas/
│   └── nombre_archivo.enc
```

- Los archivos se guardan cifrados con Fernet.
- Las extensiones terminan en `.enc` para evitar que Windows los abra como imágenes normales.
- No deben verse como imágenes convencionales si el usuario no está autenticado o si se accede directamente a la estructura local.

## Seguridad implementada
- hash seguro de contraseñas
- sesiones con protección básica
- rutas protegidas por login
- protección CSRF
- validación de campos del producto
- validación real del contenido del archivo con Pillow
- rechazo de archivos corruptos o no válidos
- rechazo de URLs internas, privadas o localhost para evitar SSRF
- límite máximo 10 MB por imagen
- archivos locales cifrados y ocultos como `.enc`
- archivos grandes comprimidos antes de almacenamiento extra

## Cómo probar la aplicación
### 1) Iniciar bases de datos
Asegúrate de que:
- MySQL esté funcionando
- MongoDB esté funcionando
- la base de datos `mercancia` exista o pueda ser creada por la aplicación

### 2) Ejecutar la aplicación
Desde la raíz del proyecto:

```powershell
cd "C:\Users\nicom\Desktop\SEPTIMO SEMESTRE\Programacion Avanzada\Primer corte\proyecto_4"
.\env\Scripts\activate
python app.py
```

### 3) Registro e inicio de sesión
Abre en el navegador:
- http://localhost:5000/register
- crea un usuario con una contraseña segura
- luego entra a http://localhost:5000/login

Cuando inicies sesión, se te redireccionará a:
- http://localhost:5000/productos

### 4) Probar la vista de productos
En la pantalla principal:
- verás la tabla con los productos
- existe un botón para agregar producto
- existe un botón para cerrar sesión
- cada fila debe mostrar la imagen del producto si la tiene

La imagen debe cargarse con una ruta protegida del backend, por ejemplo:
- http://localhost:5000/imagen/mysql/1
- http://localhost:5000/imagen/mongo/<id_archivo>

No debes entrar directamente a la carpeta local `images` como una vista pública. Esa estructura es interna y está cifrada.

### 5) Probar una imagen pequeña
Crea un producto con una imagen pequeña (menor a 1 MB). La aplicación debe:
- guardar la imagen en MySQL
- mostrarla en la tabla de productos desde la ruta protegida
- no depender de una ruta física pública

### 6) Probar una imagen grande
Crea un producto con una imagen grande (> 1 MB):
- si está entre 1 MB y 3 MB, la imagen se guarda en MongoDB/GridFS
- en la tabla debe verse la URL de la imagen y un botón para abrir la vista previa
- si supera 3 MB, además se genera una versión comprimida y la tabla debe seguir mostrando la URL junto con el botón para ver la imagen original
- la imagen original queda restringida a la lógica interna del sistema y nunca como vista pública en la carpeta local

Prueba una imagen de 2 MB y otra de 3+ MB para confirmar que la tabla muestra la URL con botón en ambos casos y que la imagen grande no se expone como vista directa en el listado.

### 7) Verificar la encriptación local
Después de guardar imágenes grandes, revisa la carpeta `images`:

```text
images/
├── original/
│   └── nombre.enc
├── comprimidas/
│   └── nombre.enc
```

Observaciones:
- los archivos terminan en `.enc`
- no deben convertirse en una vista visible para el usuario por navegación directa
- solo deben existir como respaldo cifrado del sistema

### 8) Probar validaciones de seguridad
Prueba estas situaciones:
- subir un archivo que no sea imagen
- subir una imagen muy grande (> 10 MB)
- poner una URL inadecuada o privada
- intentar entrar a /productos sin iniciar sesión

Si todo está bien, la app debe rechazar esas acciones con mensajes de error o redirección a login.

### 9) Ejecutar la batería de pruebas
En la raíz del proyecto ejecuta:

```powershell
python -m unittest tests.test_app -v
```

Esto valida:
- registro y login
- cierre de sesión
- CRUD de productos
- acceso a rutas protegidas
- carga de imágenes locales
- rechazo de archivos inválidos
- límite de tamaño 10 MB
- bloqueo de URLs privadas
- clasificación según tamaño
- almacenamiento en GridFS
- URL + botón para imágenes > 1 MB
- acceso explícito a la imagen original desde popup/modal
- almacenamiento cifrado en local
- carpeta de imágenes comprimidas

### 10) Editar una imagen existente
Cuando se quiera cambiar la imagen de un producto ya registrado:
1. abrir el producto en edición
2. eliminar o limpiar la URL existente que estaba asociada a esa imagen
3. volver a seleccionar la nueva imagen desde el equipo
4. guardar el producto

Esto es importante porque la aplicación crea una nueva referencia de imagen cuando la URL anterior ya no está disponible o no se limpia. Si no se elimina la URL previa, la nueva imagen puede quedar asociada a una referencia antigua o la edición puede no regenerar correctamente la nueva ruta.

### 11) Resultado esperado final
El sistema debe mostrar:
- login funcional
- productos con imagenes visibles desde la app
- imagen pequeña en MySQL
- imagen grande en MongoDB/GridFS
- copias locales cifradas bajo `images`
- acceso protegido solo con sesión activa

## Observaciones importantes
- La lógica de imágenes está centralizada en [src/services/imagen_service.py](src/services/imagen_service.py).
- El acceso a imágenes por rutas locales está restringido y debe trabajarse con sesión autenticada.
- Los archivos en `images` no deben ser tratados como vista pública sin control de acceso.
- La prueba de regresión confirma que el almacenamiento de imágenes cumple con los tamaños y el flujo solicitado.

## Resultado esperado
El proyecto queda preparado para cumplir con la entrega pedida: autenticación, CRUD, validación segura de imágenes, almacenamiento en MySQL y MongoDB/GridFS, cifrado local de imágenes y soporte para archivos comprimidos grandes.
