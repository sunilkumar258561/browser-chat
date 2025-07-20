/* ----------  CONFIG  ---------- */
let socket;
let currentRoom = 'General';
let username;
let roomMessages = {};
let isConnected = false;

/* ----------  CONNECTION SETUP  ---------- */
function initSocket() {
    // Use current domain for production, localhost for development
    const socketUrl = window.location.hostname === 'localhost' 
        ? 'http://localhost:3000' 
        : window.location.origin;
    
    socket = io(socketUrl, {
        transports: ['websocket', 'polling'],
        timeout: 20000,
        autoConnect: true,
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionAttempts: 5
    });

    setupSocketListeners();
}

function setupSocketListeners() {
    socket.on('connect', () => {
        console.log('Connected to server');
        isConnected = true;
        hideConnectionError();
        updateConnectionStatus('Connected', true);
        
        // Send username to server
        if (username) {
            socket.emit('set_username', username);
        }
        
        joinRoom('General');
        highlightActiveRoom('General');
    });

    socket.on('connect_error', (error) => {
        console.error('Connection failed:', error);
        isConnected = false;
        showConnectionError('Unable to connect to chat server. Please refresh the page.');
        updateConnectionStatus('Connection Failed', false);
    });

    socket.on('disconnect', (reason) => {
        console.log('Disconnected:', reason);
        isConnected = false;
        showConnectionError('Connection lost. Attempting to reconnect...');
        updateConnectionStatus('Reconnecting...', false);
    });

    socket.on('reconnect', () => {
        console.log('Reconnected successfully');
        isConnected = true;
        hideConnectionError();
        updateConnectionStatus('Connected', true);
    });

    socket.on('message', (data) => {
        addMessage(data.username, data.msg, data.username === username ? 'own' : 'other', data.timestamp);
    });

    socket.on('private_message', (data) => {
        addMessage(data.from, `[Private] ${data.msg}`, 'private', data.timestamp);
        showNotification('Private Message', `${data.from}: ${data.msg}`);
    });

    socket.on('status', (data) => {
        addMessage('System', data.msg, 'system', data.timestamp);
    });

    socket.on('active_users', (data) => {
        updateUserList(data.users);
    });

    // New private chat handlers
    socket.on('private_chat_request', (data) => {
        handlePrivateChatRequest(data.from);
    });

    socket.on('private_chat_response', (data) => {
        handlePrivateChatResponse(data.from, data.accepted);
    });
}

/* ----------  UI HELPERS  ---------- */
function showConnectionError(message) {
    let errorDiv = document.getElementById('connection-error');
    if (!errorDiv) {
        errorDiv = document.createElement('div');
        errorDiv.id = 'connection-error';
        errorDiv.style.cssText = `
            position: fixed;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            background: #dc3545;
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            z-index: 1000;
            font-weight: 500;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            animation: slideDown 0.3s ease;
        `;
        document.body.appendChild(errorDiv);
    }
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
}

function hideConnectionError() {
    const errorDiv = document.getElementById('connection-error');
    if (errorDiv) {
        errorDiv.style.display = 'none';
    }
}

function updateConnectionStatus(status, connected) {
    const statusElement = document.getElementById('connection-status');
    if (statusElement) {
        statusElement.textContent = status;
        statusElement.className = connected ? 'connected' : 'disconnected';
    }
}

function showNotification(title, message) {
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, {
            body: message,
            icon: '/static/chat-icon.png', // Add your icon
            tag: 'chat-notification'
        });
    }
}

/* ----------  USER LIST  ---------- */
function updateUserList(users) {
    const userList = document.getElementById('active-users');
    if (!userList) return;

    userList.innerHTML = users
        .map(user => {
            const isCurrentUser = user === username;
            return `
                <div class="user-item ${isCurrentUser ? 'current-user' : ''}" 
                     onclick="${!isCurrentUser ? `startPrivateChat('${user}')` : ''}"
                     title="${!isCurrentUser ? 'Click to start private chat' : 'This is you'}">
                    <div class="user-avatar">${user.charAt(0).toUpperCase()}</div>
                    <div class="user-info">
                        <span class="user-name">${user}</span>
                        ${isCurrentUser ? '<span class="user-tag">(you)</span>' : ''}
                        <div class="user-status">online</div>
                    </div>
                </div>
            `;
        })
        .join('');
}

/* ----------  MESSAGE HANDLING  ---------- */
function avatarURL(sender) {
    return `https://ui-avatars.com/api/?name=${encodeURIComponent(sender)}&background=random&color=fff&size=32`;
}

function formatTimestamp(timestamp) {
    const date = timestamp ? new Date(timestamp) : new Date();
    const now = new Date();
    
    if (date.toDateString() === now.toDateString()) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else {
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
}

function addMessage(sender, message, type, timestamp) {
    if (!roomMessages[currentRoom]) {
        roomMessages[currentRoom] = [];
    }
    
    const messageData = { sender, message, type, timestamp: timestamp || new Date().toISOString() };
    roomMessages[currentRoom].push(messageData);

    const chat = document.getElementById('chat');
    const div = document.createElement('div');
    div.className = `message ${type}`;

    if (type === 'system') {
        div.innerHTML = `
            <div class="system-message">${message}</div>
        `;
    } else {
        const avatarHtml = (type === 'other' || type === 'private')
            ? `<img class="avatar" src="${avatarURL(sender)}" alt="${sender}" loading="lazy">`
            : '';

        div.innerHTML = `
            ${avatarHtml}
            <div class="bubble">
                <div class="sender-name">${sender}</div>
                <p class="text">${escapeHtml(message)}</p>
                <span class="meta">${formatTimestamp(messageData.timestamp)}</span>
            </div>
        `;
    }

    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;

    // Show notification if window is not focused
    if (document.hidden && sender !== username && type !== 'system') {
        showNotification('New Message', `${sender}: ${message}`);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/* ----------  ACTIONS  ---------- */
function sendMessage() {
    if (!isConnected) {
        showConnectionError('Not connected to server. Please wait for reconnection.');
        return;
    }

    const input = document.getElementById('message');
    const message = input.value.trim();
    if (!message) return;

    if (message.startsWith('@')) {
        const [target, ...msgParts] = message.substring(1).split(' ');
        const privateMsg = msgParts.join(' ');
        if (privateMsg && target) {
            socket.emit('message', { 
                msg: privateMsg, 
                type: 'private', 
                target: target.trim()
            });
            // Add to local display
            addMessage(username, `[Private to ${target}] ${privateMsg}`, 'own');
        }
    } else {
        socket.emit('message', { msg: message, room: currentRoom });
    }
    
    input.value = '';
    input.focus();
}

function joinRoom(room) {
    if (!isConnected) return;
    
    socket.emit('leave', { room: currentRoom });
    currentRoom = room;
    socket.emit('join', { room });
    highlightActiveRoom(room);

    const chat = document.getElementById('chat');
    chat.innerHTML = '';
    
    // Restore messages for this room
    if (roomMessages[room]) {
        roomMessages[room].forEach(msg => {
            addMessage(msg.sender, msg.message, msg.type, msg.timestamp);
        });
    }
}

function insertPrivateMessage(user) {
    const input = document.getElementById('message');
    input.value = `@${user} `;
    input.focus();
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

/* ----------  PRIVATE CHAT FEATURES  ---------- */
function startPrivateChat(user) {
    if (user === username) return;
    
    if (isConnected) {
        socket.emit('private_chat_request', { from: username, to: user });
    }
    
    // Also insert @user in message input
    insertPrivateMessage(user);
}

function handlePrivateChatRequest(from) {
    const accept = confirm(`${from} wants to start a private chat. Accept?`);
    if (isConnected) {
        socket.emit('private_chat_response', { from: username, to: from, accepted: accept });
    }
    if (accept) {
        insertPrivateMessage(from);
    }
}

function handlePrivateChatResponse(from, accepted) {
    if (accepted) {
        showNotification('Private Chat', `${from} accepted your private chat request`);
        insertPrivateMessage(from);
    } else {
        showNotification('Private Chat', `${from} declined your private chat request`);
    }
}

/* ----------  SEARCH FUNCTIONALITY  ---------- */
function searchUsers() {
    const input = document.getElementById('userSearch');
    if (!input) return;
    
    const searchTerm = input.value.toLowerCase();
    const users = document.querySelectorAll('#active-users .user-item');
    
    users.forEach(userItem => {
        const userName = userItem.querySelector('.user-name');
        if (userName) {
            const userText = userName.textContent.toLowerCase();
            userItem.style.display = userText.includes(searchTerm) ? 'flex' : 'none';
        }
    });
}

/* ----------  INITIALIZATION  ---------- */
document.addEventListener('DOMContentLoaded', () => {
    // Get username from DOM
    const usernameElement = document.getElementById('username');
    if (usernameElement) {
        username = usernameElement.textContent.trim();
        console.log('Username:', username);
    } else {
        console.error('Username element not found');
        showConnectionError('Username not found. Please refresh the page.');
        return;
    }

    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }

    // Initialize socket connection
    initSocket();

    // Add connection status indicator if it doesn't exist
    if (!document.getElementById('connection-status')) {
        const statusDiv = document.createElement('div');
        statusDiv.id = 'connection-status';
        statusDiv.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 8px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            z-index: 999;
            transition: all 0.3s ease;
        `;
        document.body.appendChild(statusDiv);
    }

    // Focus message input
    const messageInput = document.getElementById('message');
    if (messageInput) {
        messageInput.focus();
    }
});

// Add CSS for connection status
const style = document.createElement('style');
style.textContent = `
    .connected {
        background: #28a745;
        color: white;
    }
    .disconnected {
        background: #dc3545;
        color: white;
    }
    @keyframes slideDown {
        from { transform: translate(-50%, -100%); opacity: 0; }
        to { transform: translate(-50%, 0); opacity: 1; }
    }
`;
document.head.appendChild(style);