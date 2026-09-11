import os
from flask import Flask

from src.controllers.controller import productos_c
from src.models.model_productos import Producto
from src.models.model_usuarios import Usuario

app = Flask(__name__, template_folder='src/templates')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or 'dev-secret-key-change-me'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'


@app.errorhandler(413)
def handle_413(error):
    return 'La imagen supera el límite permitido de 10 MB.', 413


app.register_blueprint(productos_c)

Usuario.inicializar_tabla()
Producto.inicializar_tabla()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
