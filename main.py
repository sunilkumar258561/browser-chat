import os
import random
import string
from datetime import datetime

from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_session import Session

# Patch eventlet before anything else
import eventlet
eventlet.monkey_patch()

# App configuration
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['DEBUG'] = True

Session(app)

# Use eventlet explicitly
socketio = SocketIO(app, async_mode='eventlet', manage_session=False)

# In-memory storage
users = {}
rooms = {"General": []}

@app.route('/')
def index():
    return render_template('index.html', rooms=rooms)

@app.route('/chat/<username>')
def chat(username):
    return render_template('chat.html', username=username, rooms=rooms)

@socketio.on('join')
def handle_join(data):
    username = data['username']
    room = data['room']
    join_room(room)
    users[request.sid] = {'username': username, 'room': room}
    emit('user_joined', {'username': username}, room=room)
    print(f"{username} joined {room}")

@socketio.on('message')
def handle_message(data):
    username = data['username']
    msg = data['msg']
    room = data['room']
    timestamp = datetime.now().strftime('%H:%M')
    rooms[room].append({'username': username, 'msg': msg, 'time': timestamp})
    emit('new_message', {'username': username, 'msg': msg, 'time': timestamp}, room=room)

@socketio.on('disconnect')
def handle_disconnect():
    user = users.pop(request.sid, None)
    if user:
        emit('user_left', {'username': user['username']}, room=user['room'])
        print(f"{user['username']} left {user['room']}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
