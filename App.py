# APP.py
from flask import Flask, request, jsonify
import psycopg2 as psycopg
import bcrypt
from flask_cors import CORS
import json
from datetime import datetime
import random
import os

# Inicialización de la aplicación Flask y configuración CORS
app = Flask(__name__)
CORS(app)

# Configuración de la conexión a la base de datos PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")
def get_db_connection():
    try:
        conn = psycopg.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Error al conectar a la base de datos: {e}")
        return None

def create_tables():
    conn = get_db_connection()
    if conn is None:
        print("Error en la conexión a la base de datos. No se pueden crear las tablas.")
        return

    with conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reference_metrics (
                    id SERIAL PRIMARY KEY,
                    avg_attention FLOAT,
                    avg_gaze_x FLOAT,
                    avg_gaze_y FLOAT,
                    computed_date TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_metrics (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    session_date TIMESTAMP,
                    avg_attention FLOAT,
                    avg_gaze_x FLOAT,
                    avg_gaze_y FLOAT,
                    raw_data JSONB
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comparative_results (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    session_metric_id INTEGER REFERENCES session_metrics(id),
                    diff_attention FLOAT,
                    diff_gaze_x FLOAT,
                    diff_gaze_y FLOAT,
                    comparison_date TIMESTAMP,
                    raw_comparison JSONB
                )
            ''')
            conn.commit()
    conn.close()
    print("Tablas creadas o verificadas correctamente.")

# Verificar la conexión y crear tablas al iniciar el servidor
if get_db_connection() is None:
    print("No se pudo establecer la conexión a la base de datos. El servidor no se iniciará.")
else:
    create_tables()
    print("El servidor está listo para recibir peticiones.")

# =====================================================
# Ruta para registrar un nuevo usuario
# =====================================================
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'message': 'Error en la conexión a la base de datos'}), 500

    with conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
            user = cursor.fetchone()

            if user:
                print("El usuario ya existe")
                return jsonify({'success': False, 'message': 'El usuario ya existe'}), 400

            # Hashear la contraseña
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            hashed_password_str = hashed_password.decode('utf-8')
            cursor.execute('INSERT INTO users (email, password) VALUES (%s, %s)', (email, hashed_password_str))
            conn.commit()

    conn.close()
    print("Usuario registrado correctamente")
    return jsonify({'success': True, 'message': 'Usuario registrado correctamente'}), 201

# =====================================================
# Ruta para iniciar sesión
# =====================================================
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'message': 'Error en la conexión a la base de datos'}), 500

    with conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
            user = cursor.fetchone()

            if not user:
                return jsonify({'success': False, 'message': 'Usuario no encontrado'}), 400

            stored_password = user[2]  # Se asume que la contraseña está en el tercer campo (índice 2)
            if not bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8')):
                return jsonify({'success': False, 'message': 'Credenciales incorrectas'}), 400

    conn.close()
    # En lugar de retornar un token, se retorna el user_id para identificar al usuario
    return jsonify({'success': True, 'user_id': user[0]}), 200

# =====================================================
# Ruta para guardar los datos de la sesión y realizar la comparación automática
# =====================================================
@app.route('/save_session_data', methods=['POST'])
@app.route('/save_session_data', methods=['POST'])
def save_session_data():
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'user_id no proporcionado'}), 400

    try:
        # Cálculo de promedios para datos de Morphcast
        morphcast_data = data.get('session_data', {}).get('morphcast', [])
        if morphcast_data:
            attention_values = [mcast.get('data', {}).get('attention', {}).get('avg', 0) for mcast in morphcast_data]
            avg_attention = sum(attention_values) / len(attention_values) if attention_values else 0
        else:
            avg_attention = 0

        # Cálculo de promedios para datos de GazeRecorder
        gaze_data = data.get('session_data', {}).get('gazeRecorder', [])
        if gaze_data:
            gaze_x_values = [gaze.get('data', {}).get('x', 0) for gaze in gaze_data]
            gaze_y_values = [gaze.get('data', {}).get('y', 0) for gaze in gaze_data]
            avg_x = sum(gaze_x_values) / len(gaze_x_values) if gaze_x_values else 0
            avg_y = sum(gaze_y_values) / len(gaze_y_values) if gaze_y_values else 0
        else:
            avg_x = avg_y = 0

        conn = get_db_connection()
        if conn is None:
            return jsonify({'success': False, 'message': 'Error en la conexión a la base de datos'}), 500

        with conn:
            with conn.cursor() as cursor:
                cursor.execute(''' 
                    CREATE TABLE IF NOT EXISTS session_metrics (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id),
                        session_date TIMESTAMP,
                        avg_attention FLOAT,
                        avg_gaze_x FLOAT,
                        avg_gaze_y FLOAT,
                        raw_data JSONB
                    )
                ''')

                cursor.execute('''
                    INSERT INTO session_metrics 
                    (user_id, session_date, avg_attention, avg_gaze_x, avg_gaze_y, raw_data)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (
                    user_id,
                    datetime.now(),
                    round(avg_attention, 2),
                    round(avg_x, 2),
                    round(avg_y, 2),
                    json.dumps(data)
                ))
                session_metric_id = cursor.fetchone()[0]
                conn.commit()

                cursor.execute('''
                    SELECT avg_attention, avg_gaze_x, avg_gaze_y FROM reference_metrics 
                    ORDER BY computed_date DESC LIMIT 1
                ''')
                reference = cursor.fetchone()

                if reference:
                    ref_avg_attention, ref_avg_gaze_x, ref_avg_gaze_y = reference
                    diff_attention = round(avg_attention - ref_avg_attention, 2)
                    diff_gaze_x = round(avg_x - ref_avg_gaze_x, 2)
                    diff_gaze_y = round(avg_y - ref_avg_gaze_y, 2)

                    comparison_data = {
                        'session_metric': {
                            'id': session_metric_id,
                            'avg_attention': round(avg_attention, 2),
                            'avg_gaze_x': round(avg_x, 2),
                            'avg_gaze_y': round(avg_y, 2)
                        },
                        'reference_metric': {
                            'avg_attention': ref_avg_attention,
                            'avg_gaze_x': ref_avg_gaze_x,
                            'avg_gaze_y': ref_avg_gaze_y
                        },
                        'differences': {
                            'diff_attention': diff_attention,
                            'diff_gaze_x': diff_gaze_x,
                            'diff_gaze_y': diff_gaze_y
                        }
                    }

                    cursor.execute('''
                        INSERT INTO comparative_results 
                        (user_id, session_metric_id, diff_attention, diff_gaze_x, diff_gaze_y, comparison_date, raw_comparison)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    ''', (
                        user_id,
                        session_metric_id,
                        diff_attention,
                        diff_gaze_x,
                        diff_gaze_y,
                        datetime.now(),
                        json.dumps(comparison_data)
                    ))
                    comparison_id = cursor.fetchone()[0]
                    conn.commit()
                else:
                    comparison_data = None
                    comparison_id = None

        conn.close()

        response = {
            'success': True,
            'message': 'Datos de sesión guardados exitosamente',
            'session_metric_id': session_metric_id
        }
        if comparison_data:
            response.update({
                'comparison_id': comparison_id,
                'comparison': comparison_data
            })
        else:
            response.update({
                'message': 'Datos de sesión guardados, pero no hay métricas de referencia para comparación'
            })

        return jsonify(response), 200

    except Exception as e:
        print(f"Error al guardar datos y realizar comparación: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# =====================================================
# Ruta para obtener los resultados del dashboard
# =====================================================
@app.route('/get_results', methods=['GET'])
def get_results():
    print("Solicitud recibida en /get_results")
    user_id = request.args.get('user_id')
    if not user_id:
        print("user_id no proporcionado")
        return jsonify({'success': False, 'message': 'user_id no proporcionado'}), 400
    try:
        user_id = int(user_id)
    except ValueError:
        print("user_id inválido")
        return jsonify({'success': False, 'message': 'user_id inválido'}), 400

    conn = get_db_connection()
    if conn is None:
        print("Error en la conexión a la base de datos")
        return jsonify({'success': False, 'message': 'Error en la conexión a la base de datos'}), 500

    with conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT id, user_id, session_date, avg_attention, avg_gaze_x, avg_gaze_y, raw_data 
                FROM session_metrics 
                WHERE user_id = %s 
                ORDER BY session_date DESC LIMIT 1
            ''', (user_id,))
            session_data = cursor.fetchone()
            if session_data:
                session_result = {
                    'id': session_data[0],
                    'user_id': session_data[1],
                    'session_date': session_data[2].isoformat(),
                    'avg_attention': session_data[3],
                    'avg_gaze_x': session_data[4],
                    'avg_gaze_y': session_data[5],
                    'raw_data': session_data[6]
                }
            else:
                session_result = None

            cursor.execute('''
                SELECT id, avg_attention, avg_gaze_x, avg_gaze_y, computed_date 
                FROM reference_metrics 
                ORDER BY computed_date DESC LIMIT 1
            ''')
            reference_data = cursor.fetchone()
            if reference_data:
                reference_result = {
                    'id': reference_data[0],
                    'avg_attention': reference_data[1],
                    'avg_gaze_x': reference_data[2],
                    'avg_gaze_y': reference_data[3],
                    'computed_date': reference_data[4].isoformat()
                }
            else:
                reference_result = None

            comparative_result = None
            if session_result:
                cursor.execute('''
                    SELECT id, user_id, session_metric_id, diff_attention, diff_gaze_x, diff_gaze_y, comparison_date, raw_comparison 
                    FROM comparative_results 
                    WHERE user_id = %s AND session_metric_id = %s 
                    ORDER BY comparison_date DESC LIMIT 1
                ''', (user_id, session_result['id']))
                comp_data = cursor.fetchone()
                if comp_data:
                    comparative_result = {
                        'id': comp_data[0],
                        'user_id': comp_data[1],
                        'session_metric_id': comp_data[2],
                        'diff_attention': comp_data[3],
                        'diff_gaze_x': comp_data[4],
                        'diff_gaze_y': comp_data[5],
                        'comparison_date': comp_data[6].isoformat(),
                        'raw_comparison': comp_data[7]
                    }

    conn.close()
    return jsonify({
        'success': True,
        'sessionData': session_result,
        'referenceData': reference_result,
        'comparativeData': comparative_result
    }), 200

@app.route('/get_users', methods=['GET'])
def get_users():
    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'message': 'Error en la conexión a la base de datos'}), 500

    with conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, email FROM users')
            users = cursor.fetchall()

    conn.close()

    if users:
        user_list = [{'id': user[0], 'email': user[1]} for user in users]
        return jsonify({'success': True, 'users': user_list}), 200
    else:
        return jsonify({'success': False, 'message': 'No se encontraron usuarios'}), 404

# =====================================================
# Inicio del servidor
# =====================================================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
