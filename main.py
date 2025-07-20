# Imports here
import os
import random
import logging
from datetime import datetime
from typing import Dict

from flask import Flask, render_template, request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.middleware.proxy_fix import ProxyFix

# App Configuration Settings
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24)
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')
    CHAT_ROOMS = ['General', 'Introductions', 'off-topics', 'Hobbies and sports']
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Initialize SocketIO with Render-optimized settings
socketio = SocketIO(
    app,
    cors_allowed_origins=app.config['CORS_ORIGINS'],
    async_mode='threading',
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25,
    transport=['websocket', 'polling'],  # Ensure both transports work
    allow_upgrades=True
)

# Config logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# In-memory user tracking
active_users: Dict[str, dict] = {}

def generate_guest_username() -> str:
    timestamp = datetime.now().strftime('%H%M')
    return f'user{timestamp}{random.randint(1000,9999)}'

def get_users_in_room(room):
    """Get list of users in a specific room"""
    return [user for user in active_users.values() if user.get('room') == room]

def get_all_active_users():
    """Get all active users with their details"""
    return [{'username': user['username'], 'room': user.get('room', 'General')} 
            for user in active_users.values()]

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
        # Force session persistence
        session.permanent = True
        
        if 'username' not in session:
            session['username'] = generate_guest_username()
        
        username = session['username']
        
        # Add user to active users with more details
        active_users[request.sid] = {
            'username': username,
            'connected_at': datetime.now().isoformat(),
            'room': 'General',
            'sid': request.sid  # Store SID for debugging
        }
        
        # Join default room
        join_room('General')
        
        # Log connection details
        logger.info(f"User connected: {username} (SID: {request.sid})")
        logger.info(f"Total active users: {len(active_users)}")
        
        # Send immediate confirmation to the connecting user
        emit('connection_confirmed', {
            'username': username,
            'room': 'General',
            'message': 'Connected successfully'
        })
        
        # Send current user list to the newly connected user (immediate)
        all_users = get_all_active_users()
        emit('active_users', {
            'users': all_users,
            'count': len(all_users)
        })
        
        # Send users in current room to the newly connected user
        room_users = get_users_in_room('General')
        emit('room_users', {
            'room': 'General',
            'users': [user['username'] for user in room_users],
            'count': len(room_users)
        })
        
        # Small delay then broadcast to others
        socketio.sleep(0.1)
        
        # Broadcast updated user list to all other users
        all_users_updated = get_all_active_users()
        emit('active_users', {
            'users': all_users_updated,
            'count': len(all_users_updated)
        }, broadcast=True, include_self=False)
        
        # Broadcast user joined status to the room
        emit('status', {
            'msg': f'{username} has joined the room.',
            'type': 'join',
            'timestamp': datetime.now().isoformat(),
            'username': username
        }, room='General', include_self=False)
        
        # Update room user list for everyone in General
        emit('room_users', {
            'room': 'General',
            'users': [user['username'] for user in get_users_in_room('General')],
            'count': len(get_users_in_room('General'))
        }, room='General')
        
        logger.info(f"Broadcasting complete for user: {username}")
        
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        emit('error', {'msg': 'Connection failed', 'error': str(e)})
        return False

@socketio.event
def disconnect():
    try:
        if request.sid in active_users:
            username = active_users[request.sid]['username']
            current_room = active_users[request.sid].get('room', 'General')
            
            # Remove user from active users
            del active_users[request.sid]
            
            # Broadcast updated user list to all users
            emit('active_users', {
                'users': get_all_active_users()
            }, broadcast=True)
            
            # Broadcast updated room users list
            emit('room_users', {
                'room': current_room,
                'users': [user['username'] for user in get_users_in_room(current_room)]
            }, room=current_room)
            
            # Notify room about user leaving
            emit('status', {
                'msg': f'{username} has disconnected.',
                'type': 'disconnect',
                'timestamp': datetime.now().isoformat()
            }, room=current_room)
            
            logger.info(f"User disconnected: {username}")
            
    except Exception as e:
        logger.error(f"Disconnection error: {str(e)}")

@socketio.on('join')
def on_join(data: dict):
    try:
        username = session.get('username')
        if not username:
            logger.warning("Join attempt without username in session")
            emit('error', {'msg': 'Username not found in session'})
            return
        
        room = data.get('room')
        if not room or room not in app.config['CHAT_ROOMS']:
            logger.warning(f"Invalid room join attempt: {room}")
            emit('error', {'msg': f'Invalid room: {room}'})
            return
        
        # Get current room
        current_room = None
        if request.sid in active_users:
            current_room = active_users[request.sid].get('room')
        
        # Leave current room if different
        if current_room and current_room != room:
            leave_room(current_room)
            
            # Notify old room about user leaving
            emit('status', {
                'msg': f'{username} has left the room.',
                'type': 'leave',
                'timestamp': datetime.now().isoformat()
            }, room=current_room)
            
            # Update old room's user list
            old_room_users = get_users_in_room(current_room)
            emit('room_users', {
                'room': current_room,
                'users': [user['username'] for user in old_room_users],
                'count': len(old_room_users)
            }, room=current_room)
            
            logger.info(f"User {username} left room: {current_room}")
        
        # Join new room
        join_room(room)
        
        # Update user's room in active_users
        if request.sid in active_users:
            active_users[request.sid]['room'] = room
        else:
            # User not in active_users, add them
            active_users[request.sid] = {
                'username': username,
                'connected_at': datetime.now().isoformat(),
                'room': room,
                'sid': request.sid
            }
        
        # Get updated room users list
        room_users = get_users_in_room(room)
        
        # Send room users list to the joining user first
        emit('room_users', {
            'room': room,
            'users': [user['username'] for user in room_users],
            'count': len(room_users)
        })
        
        # Confirm room join to the user
        emit('room_joined', {
            'room': room,
            'message': f'Successfully joined {room}',
            'users_count': len(room_users)
        })
        
        # Notify new room about user joining
        emit('status', {
            'msg': f'{username} has joined the room.',
            'type': 'join',
            'timestamp': datetime.now().isoformat(),
            'username': username
        }, room=room)
        
        # Update new room's user list for everyone in the room
        emit('room_users', {
            'room': room,
            'users': [user['username'] for user in room_users],
            'count': len(room_users)
        }, room=room)
        
        # Update global active users list
        emit('active_users', {
            'users': get_all_active_users(),
            'count': len(active_users)
        }, broadcast=True)
        
        logger.info(f"User {username} successfully joined room: {room}")
        logger.info(f"Room {room} now has {len(room_users)} users: {[u['username'] for u in room_users]}")
        
    except Exception as e:
        logger.error(f"Join room error: {str(e)}")
        emit('error', {'msg': f'Failed to join room: {str(e)}'})

@socketio.on('leave')
def on_leave(data: dict):
    try:
        username = session.get('username')
        if not username:
            return
            
        room = data.get('room')
        if not room:
            return
            
        leave_room(room)
        if request.sid in active_users:
            active_users[request.sid]['room'] = 'General'  # Default back to General
            join_room('General')
            
        # Notify room about user leaving
        emit('status', {
            'msg': f'{username} has left the room.',
            'type': 'leave',
            'timestamp': datetime.now().isoformat()
        }, room=room)
        
        # Update room's user list
        emit('room_users', {
            'room': room,
            'users': [user['username'] for user in get_users_in_room(room)]
        }, room=room)
        
        logger.info(f"User {username} left room: {room}")
        
    except Exception as e:
        logger.error(f"Leave room error: {str(e)}")

@socketio.on('message')
def handle_message(data: dict):
    try:
        username = session.get('username')
        if not username:
            logger.warning("Message attempt without username in session")
            emit('error', {'msg': 'Username not found in session'})
            return
        
        # Verify user is in active users
        if request.sid not in active_users:
            logger.warning(f"Message from unknown user SID: {request.sid}")
            emit('error', {'msg': 'User not properly connected'})
            return
            
        # Get current room from user data (more reliable than client data)
        current_user_room = active_users[request.sid].get('room', 'General')
        room = data.get('room', current_user_room)  # Use client room if provided, fallback to user's current room
        msg_type = data.get('type', 'message')
        message = data.get('msg', '').strip()
        
        if not message:
            logger.warning(f"Empty message from {username}")
            return
            
        timestamp = datetime.now().isoformat()
        
        # Ensure user is actually in the room they're trying to send to
        if room != current_user_room:
            logger.warning(f"User {username} trying to send to {room} but is in {current_user_room}")
            # Force join the room they're trying to send to
            join_room(room)
            active_users[request.sid]['room'] = room
        
        if msg_type == 'private':
            target_user = data.get('target')
            if not target_user:
                return
                
            # Find target user's socket ID
            target_sid = None
            for sid, user_data in active_users.items():
                if user_data['username'] == target_user:
                    target_sid = sid
                    break
            
            if target_sid:
                # Send to target user
                emit('private_message', {
                    'msg': message,
                    'from': username,
                    'to': target_user,
                    'timestamp': timestamp
                }, room=target_sid)
                
                # Send confirmation to sender
                emit('private_message', {
                    'msg': message,
                    'from': username,
                    'to': target_user,
                    'timestamp': timestamp,
                    'sent_by_me': True
                })
                
                logger.info(f"Private message sent: {username} -> {target_user}")
            else:
                logger.warning(f"Private message failed - user not found: {target_user}")
                emit('error', {'msg': f'User {target_user} not found'})
        else:
            # Public room message
            if room not in app.config['CHAT_ROOMS']:
                logger.warning(f"Message to invalid room: {room}")
                emit('error', {'msg': f'Invalid room: {room}'})
                return
            
            # Create message object
            message_data = {
                'msg': message,
                'username': username,
                'room': room,
                'timestamp': timestamp,
                'sid': request.sid  # For debugging
            }
            
            # Log detailed info for debugging
            users_in_room = get_users_in_room(room)
            logger.info(f"Broadcasting message in {room}: '{message[:50]}...' from {username}")
            logger.info(f"Users in {room}: {[u['username'] for u in users_in_room]}")
            logger.info(f"Total users in room: {len(users_in_room)}")
            
            # Broadcast to ALL users in the room (including sender for confirmation)
            emit('message', message_data, room=room)
            
            # Also broadcast to ensure everyone gets it (backup method)
            for sid, user_data in active_users.items():
                if user_data.get('room') == room:
                    emit('message', message_data, room=sid)
            
            logger.info(f"Message broadcast complete for {room}")
            
    except Exception as e:
        logger.error(f"Message handling error: {str(e)}")
        emit('error', {'msg': f'Message sending failed: {str(e)}'})

@socketio.on('private_chat_request')
def handle_private_request(data):
    try:
        to_user = data.get('to')
        from_user = data.get('from')
        if not to_user or not from_user:
            return
            
        # Find target user's socket ID
        target_sid = None
        for sid, user_data in active_users.items():
            if user_data['username'] == to_user:
                target_sid = sid
                break
        
        if target_sid:
            emit('private_chat_request', {'from': from_user}, room=target_sid)
            logger.info(f"Private chat request sent: {from_user} -> {to_user}")
        else:
            logger.warning(f"Private chat request failed - user not found: {to_user}")
            emit('error', {'msg': f'User {to_user} not found'})
            
    except Exception as e:
        logger.error(f"Private chat request error: {str(e)}")

@socketio.on('private_chat_response')
def handle_private_response(data):
    try:
        to_user = data.get('to')
        from_user = data.get('from')
        accepted = data.get('accepted', False)
        
        if not to_user or not from_user:
            return
        
        # Find target user's socket ID
        target_sid = None
        for sid, user_data in active_users.items():
            if user_data['username'] == to_user:
                target_sid = sid
                break
        
        if target_sid:
            emit('private_chat_response', {
                'from': from_user, 
                'accepted': accepted
            }, room=target_sid)
            logger.info(f"Private chat response sent: {from_user} -> {to_user} (accepted: {accepted})")
        else:
            logger.warning(f"Private chat response failed - user not found: {to_user}")
            
    except Exception as e:
        logger.error(f"Private chat response error: {str(e)}")

@socketio.on('set_username')
def set_username(data):
    try:
        username = data.get('username', '').strip() if isinstance(data, dict) else str(data).strip()
        if username and request.sid in active_users:
            old_username = active_users[request.sid]['username']
            active_users[request.sid]['username'] = username
            session['username'] = username
            
            current_room = active_users[request.sid].get('room', 'General')
            
            # Broadcast username change to current room
            emit('status', {
                'msg': f'{old_username} is now known as {username}.',
                'type': 'username_change',
                'timestamp': datetime.now().isoformat()
            }, room=current_room)
            
            # Update active users list for all clients
            emit('active_users', {
                'users': get_all_active_users()
            }, broadcast=True)
            
            # Update room users list
            emit('room_users', {
                'room': current_room,
                'users': [user['username'] for user in get_users_in_room(current_room)]
            }, room=current_room)
            
            logger.info(f"Username updated: {old_username} -> {username}")
            
    except Exception as e:
        logger.error(f"Set username error: {str(e)}")

# Add periodic user list broadcast
@socketio.on('heartbeat')
def handle_heartbeat():
    """Handle client heartbeat and send user list"""
    try:
        if request.sid in active_users:
            username = active_users[request.sid]['username']
            current_room = active_users[request.sid].get('room', 'General')
            
            # Send fresh user lists
            emit('active_users', {
                'users': get_all_active_users(),
                'count': len(get_all_active_users())
            })
            
            emit('room_users', {
                'room': current_room,
                'users': [user['username'] for user in get_users_in_room(current_room)],
                'count': len(get_users_in_room(current_room))
            })
            
            logger.info(f"Heartbeat from {username}, sent fresh user lists")
        else:
            logger.warning(f"Heartbeat from unknown SID: {request.sid}")
            
    except Exception as e:
        logger.error(f"Heartbeat error: {str(e)}")

@socketio.on('refresh_users')
def handle_refresh_users():
    """Handle explicit user list refresh request"""
    try:
        if request.sid in active_users:
            current_room = active_users[request.sid].get('room', 'General')
            
            # Force refresh of user lists
            all_users = get_all_active_users()
            room_users = get_users_in_room(current_room)
            
            emit('active_users', {
                'users': all_users,
                'count': len(all_users),
                'refreshed': True
            })
            
            emit('room_users', {
                'room': current_room,
                'users': [user['username'] for user in room_users],
                'count': len(room_users),
                'refreshed': True
            })
            
            logger.info(f"Manual refresh requested by {active_users[request.sid]['username']}")
        
    except Exception as e:
        logger.error(f"Refresh users error: {str(e)}")

@socketio.on('get_active_users')
def get_active_users():
    try:
        users = get_all_active_users()
        emit('active_users', {
            'users': users,
            'count': len(users),
            'timestamp': datetime.now().isoformat()
        })
        logger.info(f"Sent active users list: {len(users)} users")
    except Exception as e:
        logger.error(f"Get active users error: {str(e)}")

@socketio.on('get_room_users')
def get_room_users(data):
    try:
        room = data.get('room') if data else 'General'
        if room and room in app.config['CHAT_ROOMS']:
            room_users = get_users_in_room(room)
            emit('room_users', {
                'room': room,
                'users': [user['username'] for user in room_users],
                'count': len(room_users),
                'timestamp': datetime.now().isoformat()
            })
            logger.info(f"Sent room users for {room}: {len(room_users)} users")
    except Exception as e:
        logger.error(f"Get room users error: {str(e)}")

@app.route('/debug/users')
def debug_users():
    """Debug endpoint to check active users"""
    return {
        'active_users': active_users,
        'count': len(active_users),
        'timestamp': datetime.now().isoformat()
    }
@app.route('/debug/test-message', methods=['POST'])
def test_message():
    """Test endpoint to send a message to all users in a room"""
    try:
        room = request.json.get('room', 'General')
        message = request.json.get('message', 'Test message from server')
        
        if room not in app.config['CHAT_ROOMS']:
            return {'error': 'Invalid room'}, 400
            
        # Broadcast test message
        socketio.emit('message', {
            'msg': message,
            'username': 'SYSTEM',
            'room': room,
            'timestamp': datetime.now().isoformat(),
            'type': 'system'
        }, room=room)
        
        room_users = get_users_in_room(room)
        
        return {
            'success': True,
            'room': room,
            'message': message,
            'users_in_room': [u['username'] for u in room_users],
            'user_count': len(room_users)
        }
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/debug/rooms')
def debug_rooms():
    """Debug endpoint to see users in each room"""
    rooms_info = {}
    for room in app.config['CHAT_ROOMS']:
        users = get_users_in_room(room)
        rooms_info[room] = {
            'users': [u['username'] for u in users],
            'count': len(users)
        }
    
    return {
        'rooms': rooms_info,
        'total_users': len(active_users),
        'timestamp': datetime.now().isoformat()
    }

@app.route('/debug/session')
def debug_session():
    """Debug endpoint to check session"""
    return {
        'session': dict(session),
        'has_username': 'username' in session,
        'timestamp': datetime.now().isoformat()
    }

# Health check endpoint for Render
@app.route('/health')
def health_check():
    return {
        'status': 'healthy', 
        'timestamp': datetime.now().isoformat(),
        'active_users_count': len(active_users),
        'socketio_status': 'running'
    }

# Run server
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=app.config['DEBUG']
    )