import os
import random
import logging
from datetime import datetime
from typing import Dict
import eventlet
from flask import Flask, render_template, request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.middleware.proxy_fix import ProxyFix
eventlet.monkey_patch()
# Config logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# App Configuration Settings
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')
    CHAT_ROOMS = ['General', 'Introductions', 'off-topics', 'Hobbies and sports']

# Initialize Flask app
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize SocketIO with proper configuration for production
socketio = SocketIO(
    app,
    cors_allowed_origins=app.config['CORS_ORIGINS'],
    logger=False,  # Disable SocketIO logging in production
    engineio_logger=False,
    async_mode='threading',  # Use threading for better compatibility
    ping_timeout=60,
    ping_interval=25
)

# In-memory user tracking
active_users: Dict[str, dict] = {}

def generate_guest_username() -> str:
    timestamp = datetime.now().strftime('%H%M')
    return f'user{timestamp}{random.randint(1000,9999)}'

@app.route('/')
def index():
    if 'username' in session and session['username'].strip():
        return render_template('index.html', username=session['username'], rooms=app.config['CHAT_ROOMS'])
    return render_template('name_prompt.html')

@app.route('/set_name', methods=['POST'])
def set_name():
    chosen = request.form.get('username', '').strip()
    if not chosen:
        return "Name cannot be empty", 400
    session['username'] = chosen
    logger.info(f"User chose name: {chosen}")
    return '', 204

@socketio.event
def connect():
    try:
        if 'username' not in session:
            session['username'] = generate_guest_username()
        
        active_users[request.sid] = {
            'username': session['username'],
            'connected_at': datetime.now().isoformat(),
            'room': 'General'
        }
        
        join_room('General')
        
        emit('active_users', {
            'users': [user['username'] for user in active_users.values()]
        }, broadcast=True)
        
        logger.info(f"User connected: {session['username']}")
        return True
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        return False

@socketio.event
def disconnect():
    try:
        if request.sid in active_users:
            username = active_users[request.sid]['username']
            del active_users[request.sid]
            
            emit('active_users', {
                'users': [user['username'] for user in active_users.values()]
            }, broadcast=True)
            
            logger.info(f"User disconnected: {username}")
    except Exception as e:
        logger.error(f"Disconnection error: {str(e)}")

@socketio.on('join')
def on_join(data: dict):
    try:
        username = session['username']
        room = data['room']
        
        if room not in app.config['CHAT_ROOMS']:
            logger.warning(f"Invalid room join attempt: {room}")
            return
        
        join_room(room)
        active_users[request.sid]['room'] = room
        
        emit('status', {
            'msg': f'{username} has joined the room.',
            'type': 'join',
            'timestamp': datetime.now().isoformat()
        }, room=room)
        
        logger.info(f"User {username} joined room: {room}")
    except Exception as e:
        logger.error(f"Join room error: {str(e)}")

@socketio.on('leave')
def on_leave(data: dict):
    try:
        username = session['username']
        room = data['room']
        
        leave_room(room)
        
        if request.sid in active_users:
            active_users[request.sid].pop('room', None)
        
        emit('status', {
            'msg': f'{username} has left the room.',
            'type': 'leave',
            'timestamp': datetime.now().isoformat()
        }, room=room)
        
        logger.info(f"User {username} left room: {room}")
    except Exception as e:
        logger.error(f"Leave room error: {str(e)}")

@socketio.on('message')
def handle_message(data: dict):
    try:
        username = session['username']
        room = data.get('room', 'General')
        msg_type = data.get('type', 'message')
        message = data.get('msg', '').strip()
        
        if not message:
            return
        
        timestamp = datetime.now().isoformat()
        
        if msg_type == 'private':
            target_user = data.get('target')
            if not target_user:
                return
            
            # Find target user and send private message
            for sid, user_data in active_users.items():
                if user_data['username'] == target_user:
                    emit('private_message', {
                        'msg': message,
                        'from': username,
                        'to': target_user,
                        'timestamp': timestamp
                    }, room=sid)
                    logger.info(f"Private message sent: {username} -> {target_user}")
                    return
            
            logger.warning(f"Private message failed - user not found: {target_user}")
        else:
            if room not in app.config['CHAT_ROOMS']:
                logger.warning(f"Message to invalid room: {room}")
                return
            
            emit('message', {
                'msg': message,
                'username': username,
                'room': room,
                'timestamp': timestamp
            }, room=room)
            
            logger.info(f"Message sent in {room} by {username}")
    except Exception as e:
        logger.error(f"Message handling error: {str(e)}")

@socketio.on('set_username')
def set_username(username):
    try:
        session['username'] = username
        if request.sid in active_users:
            active_users[request.sid]['username'] = username
        logger.info(f"Username set: {username}")
    except Exception as e:
        logger.error(f"Set username error: {str(e)}")

# Health check endpoint for Render
@app.route('/health')
def health_check():
    return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}

# Run server
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = app.config['DEBUG']
    
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=debug_mode,
        use_reloader=debug_mode,
        log_output=True
    )