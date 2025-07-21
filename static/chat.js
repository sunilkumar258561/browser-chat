let socket = io();
let currentRoom = 'General';
let username = document.getElementById('username').textContent;
let roomMessages = {};

/* ----------  SOCKET LISTENERS  ---------- */
socket.on('connect', () => {
    console.log('Connected to server');
    joinRoom('General');
    highlightActiveRoom('General');
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
});

socket.on('connect_error', (error) => {
    console.error('Connection error:', error);
});

socket.on('message', (data) => {
    addMessage(data.username, data.msg, data.username === username ? 'own' : 'other');
});

socket.on('private_message', (data) => {
    addMessage(data.from, `[Private] ${data.msg}`, 'private');
});

socket.on('status', (data) => {
    addMessage('System', data.msg, 'system');
});

socket.on('active_users', (data) => {
    const userList = document.getElementById('active-users');
    userList.innerHTML = data.users
        .map(
            (user) => `
            <div class="user-item" onclick="insertPrivateMessage('${user}')">
                ${user} ${user === username ? '(you)' : ''}
            </div>
        `
        )
        .join('');
});

/* ----------  HELPERS  ---------- */
function avatarURL(sender) {
    return `https://i.pravatar.cc/32?u=${encodeURIComponent(sender)}`;
}

function formatTimestamp() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/* ----------  NEW BUBBLE RENDERER  ---------- */
function addMessage(sender, message, type) {
    if (!roomMessages[currentRoom]) roomMessages[currentRoom] = [];
    roomMessages[currentRoom].push({ sender, message, type });

    const chat = document.getElementById('chat');
    const div = document.createElement('div');
    div.className = `message ${type}`;

    const avatarHtml = (type === 'other' || type === 'private')
        ? `<img class="avatar" src="${avatarURL(sender)}" alt="${sender}">`
        : '';

    div.innerHTML = `
        ${avatarHtml}
        <div class="bubble">
            <p class="text">${message}</p>
            <span class="meta">${formatTimestamp()}</span>
        </div>
    `;

    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

/* ----------  ACTIONS  ---------- */
function sendMessage() {
    const input = document.getElementById('message');
    const message = input.value.trim();
    if (!message) return;

    if (message.startsWith('@')) {
        const [target, ...msgParts] = message.substring(1).split(' ');
        const privateMsg = msgParts.join(' ');
        if (privateMsg) {
            socket.emit('message', { msg: privateMsg, type: 'private', target });
        }
    } else {
        socket.emit('message', { msg: message, room: currentRoom });
    }
    input.value = '';
    input.focus();
}

function joinRoom(room) {
    socket.emit('leave', { room: currentRoom });
    currentRoom = room;
    socket.emit('join', { room });
    highlightActiveRoom(room);

    const chat = document.getElementById('chat');
    chat.innerHTML = '';
    (roomMessages[room] || []).forEach(m => addMessage(m.sender, m.message, m.type));
}

function insertPrivateMessage(user) {
    document.getElementById('message').value = `@${user} `;
    document.getElementById('message').focus();
}

function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function highlightActiveRoom(room) {
    document.querySelectorAll('.room-item').forEach(item => {
        item.classList.toggle('active-room', item.textContent.trim() === room);
    });
}

/* ----------  INIT  ---------- */
document.addEventListener('DOMContentLoaded', () => {
    if ('Notification' in window) Notification.requestPermission();
    
    // Set username on connect
    socket.emit('set_username', username);
});

function searchUsers() {
    const input = document.getElementById('userSearch');
    if (!input) return;
    
    const searchTerm = input.value.toLowerCase();
    const users = document.querySelectorAll('#active-users .user-item');
    
    users.forEach(user => {
        const username = user.textContent.toLowerCase();
        user.style.display = username.includes(searchTerm) ? 'flex' : 'none';
    });
}