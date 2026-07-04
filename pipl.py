import hashlib
import json
import os
import secrets
import threading
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, 'pipl_users.json')

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

users = {}
sessions = {}
pending_messages = {}

lock = threading.Lock()

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Простой браузерный мессенджер</title>
  <style>
    body { margin: 0; min-height: 100vh; font-family: Inter, system-ui, sans-serif; background: linear-gradient(180deg, #0f172a 0%, #020617 100%); color: #f8fafc; }
    .app-shell { max-width: 960px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 8px; font-size: 2rem; }
    p { margin: 0; color: #94a3b8; }
    .card { background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(148, 163, 184, 0.12); border-radius: 16px; padding: 18px; margin-bottom: 18px; }
    .hidden { display: none; }
    .tabs { display: flex; gap: 8px; margin-bottom: 12px; }
    .tabs button { flex: 1; border: none; background: rgba(148, 163, 184, 0.08); color: #f8fafc; padding: 10px 14px; border-radius: 999px; cursor: pointer; }
    .tabs button.active { background: #38bdf8; color: #0f172a; }
    .form-row { margin-bottom: 12px; }
    .form-row label { display: block; margin-bottom: 6px; color: #94a3b8; }
    input, textarea, button { width: 100%; font: inherit; }
    input, textarea { background: #0f172a; color: #f8fafc; border: 1px solid rgba(148, 163, 184, 0.15); border-radius: 12px; padding: 12px; }
    textarea { resize: vertical; }
    button { border: none; border-radius: 12px; padding: 12px 16px; background: #38bdf8; color: #0f172a; font-weight: 700; cursor: pointer; }
    button.secondary { background: rgba(56, 189, 248, 0.15); color: #f8fafc; }
    .toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
    #statusLine { display: inline-block; margin-right: 16px; font-weight: 700; color: #4ade80; }
    .message { color: #94a3b8; min-height: 24px; }
    .chat-window { min-height: 320px; max-height: 520px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
    .message-item { padding: 12px; border-radius: 14px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(148, 163, 184, 0.1); }
    .message-item.self { align-self: flex-end; background: rgba(56, 189, 248, 0.16); }
    .message-item .meta { margin-bottom: 6px; color: #94a3b8; font-size: 0.92rem; }
    .compose { display: grid; gap: 10px; }
    .info-panel ul { margin: 0; padding-left: 20px; }
    .wide { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 720px) { .wide { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="app-shell">
    <header>
      <h1>Простой браузерный мессенджер</h1>
      <p>Регистрация внутри приложения без почты и номера телефона.</p>
    </header>

    <section id="authSection" class="card">
      <div class="tabs">
        <button id="showLogin" class="active">Вход</button>
        <button id="showRegister">Регистрация</button>
      </div>
      <div class="form-row">
        <label>Имя</label>
        <input id="usernameInput" type="text" autocomplete="username" />
      </div>
      <div class="form-row">
        <label>Пароль</label>
        <input id="passwordInput" type="password" autocomplete="current-password" />
      </div>
      <div class="form-row buttons">
        <button id="authButton">Войти</button>
      </div>
      <div id="authMessage" class="message"></div>
    </section>

    <section id="chatSection" class="hidden">
      <div class="toolbar card">
        <div>
          <span id="statusLine">Offline</span>
          <span id="userLine"></span>
        </div>
        <button id="logoutButton" class="secondary">Выйти</button>
      </div>

      <div class="card wide">
        <div>
          <div class="form-row">
            <label>Отправить пользователю (оставьте пустым для общей комнаты)</label>
            <input id="recipientInput" type="text" placeholder="Имя друга" />
          </div>
          <div class="form-row buttons">
            <button id="bluetoothButton" class="secondary">Подключить Bluetooth</button>
          </div>
          <div id="bluetoothStatus" class="message"></div>
        </div>
        <div class="chat-window card" id="messages"></div>
      </div>

      <div class="compose card">
        <textarea id="messageInput" rows="3" placeholder="Введите текст..."></textarea>
        <button id="sendButton">Отправить</button>
      </div>

      <div class="info-panel card">
        <h2>Инструкции</h2>
        <ul>
          <li>Работает в браузере на телефоне и ПК.</li>
          <li>Сообщения отправляются через сервер, если есть интернет.</li>
          <li>Без интернета вы можете использовать Bluetooth, если браузер поддерживает Web Bluetooth.</li>
          <li>Регистрация выполняется внутри приложения по имени + паролю.</li>
        </ul>
      </div>
    </section>
  </div>

  <script>
    const state = { token: null, username: null, bluetoothDevice: null, bluetoothCharacteristic: null, queuedOffline: [] };
    const elements = {
      authSection: document.getElementById('authSection'),
      chatSection: document.getElementById('chatSection'),
      showLogin: document.getElementById('showLogin'),
      showRegister: document.getElementById('showRegister'),
      usernameInput: document.getElementById('usernameInput'),
      passwordInput: document.getElementById('passwordInput'),
      authButton: document.getElementById('authButton'),
      authMessage: document.getElementById('authMessage'),
      statusLine: document.getElementById('statusLine'),
      userLine: document.getElementById('userLine'),
      logoutButton: document.getElementById('logoutButton'),
      messages: document.getElementById('messages'),
      messageInput: document.getElementById('messageInput'),
      sendButton: document.getElementById('sendButton'),
      recipientInput: document.getElementById('recipientInput'),
      bluetoothButton: document.getElementById('bluetoothButton'),
      bluetoothStatus: document.getElementById('bluetoothStatus'),
    };

    function setStatus(text, ok = true) {
      elements.statusLine.textContent = text;
      elements.statusLine.style.color = ok ? '#4ade80' : '#f97316';
    }

    function setUserInfo(name) {
      elements.userLine.textContent = name ? `Пользователь: ${name}` : '';
    }

    function showScreen(loggedIn) {
      elements.authSection.classList.toggle('hidden', loggedIn);
      elements.chatSection.classList.toggle('hidden', !loggedIn);
    }

    function appendMessage(message, self = false) {
      const item = document.createElement('div');
      item.className = `message-item${self ? ' self' : ''}`;
      item.innerHTML = `<div class="meta">${message.from} → ${message.to || 'Все'} · ${new Date(message.timestamp).toLocaleTimeString()}</div><div>${message.text}</div>`;
      elements.messages.appendChild(item);
      elements.messages.scrollTop = elements.messages.scrollHeight;
    }

    function loadSession() {
      const data = localStorage.getItem('pipl-session');
      if (!data) return;
      try { const saved = JSON.parse(data); state.token = saved.token; state.username = saved.username; } catch (err) {}
    }

    function saveSession() {
      localStorage.setItem('pipl-session', JSON.stringify({ token: state.token, username: state.username }));
    }

    function clearSession() {
      state.token = null; state.username = null;
      localStorage.removeItem('pipl-session');
    }

    async function api(url, method = 'GET', body) {
      const headers = { 'Content-Type': 'application/json' };
      if (state.token) headers['X-Auth-Token'] = state.token;
      const opts = { method, headers };
      if (body) opts.body = JSON.stringify(body);
      const response = await fetch(url, opts);
      if (!response.ok) throw new Error('Сервер вернул ошибку ' + response.status);
      return response.json();
    }

    async function authAction(isRegister) {
      const username = elements.usernameInput.value.trim();
      const password = elements.passwordInput.value.trim();
      if (!username || !password) { elements.authMessage.textContent = 'Введите имя и пароль.'; return; }
      const url = isRegister ? '/api/register' : '/api/login';
      try {
        const result = await api(url, 'POST', { username, password });
        elements.authMessage.textContent = result.message;
        if (!isRegister && result.success) {
          state.token = result.token;
          state.username = username;
          saveSession();
          setUserInfo(username);
          showScreen(true);
          setStatus('Онлайн', true);
          startPolling();
        }
      } catch (err) {
        elements.authMessage.textContent = err.message;
      }
    }

    async function sendMessage() {
      const text = elements.messageInput.value.trim();
      if (!text) return;
      const to = elements.recipientInput.value.trim() || null;
      const message = { from: state.username, to: to || 'Все', text, timestamp: Date.now() };
      appendMessage(message, true);
      elements.messageInput.value = '';
      if (!navigator.onLine) {
        state.queuedOffline.push({ to, text });
        setStatus('Оффлайн: сообщение будет отправлено позже.', false);
        return;
      }
      try {
        await api('/api/message', 'POST', { to, text });
        setStatus('Сообщение отправлено.', true);
      } catch (err) {
        state.queuedOffline.push({ to, text });
        setStatus('Не удалось отправить, сохранено локально.', false);
      }
      if (state.bluetoothCharacteristic) {
        sendBluetooth(text);
      }
    }

    async function startPolling() {
      if (!state.token) return;
      try {
        const response = await api('/api/poll');
        if (Array.isArray(response.messages)) {
          response.messages.forEach((msg) => appendMessage(msg, msg.from === state.username));
        }
        if (!navigator.onLine) setStatus('Оффлайн. Bluetooth доступен.', false);
      } catch (err) {
        setStatus('Ошибка связи с сервером.', false);
      }
      if (navigator.onLine && state.queuedOffline.length > 0) {
        while (state.queuedOffline.length) {
          const item = state.queuedOffline.shift();
          try { await api('/api/message', 'POST', { to: item.to, text: item.text }); } catch (err) { state.queuedOffline.unshift(item); break; }
        }
      }
      setTimeout(startPolling, 1500);
    }

    async function connectBluetooth() {
      if (!navigator.bluetooth) { elements.bluetoothStatus.textContent = 'Bluetooth API не поддерживается этим браузером.'; return; }
      try {
        const device = await navigator.bluetooth.requestDevice({ acceptAllDevices: true, optionalServices: ['0000fedc-0000-1000-8000-00805f9b34fb'] });
        const server = await device.gatt.connect();
        const service = await server.getPrimaryService('0000fedc-0000-1000-8000-00805f9b34fb');
        const characteristic = await service.getCharacteristic('0000beef-0000-1000-8000-00805f9b34fb');
        await characteristic.startNotifications();
        characteristic.addEventListener('characteristicvaluechanged', (event) => {
          const decoder = new TextDecoder();
          const text = decoder.decode(event.target.value);
          appendMessage({ from: 'Bluetooth', to: state.username || 'Вы', text, timestamp: Date.now() }, false);
        });
        state.bluetoothDevice = device;
        state.bluetoothCharacteristic = characteristic;
        elements.bluetoothStatus.textContent = 'Bluetooth подключён. Сообщения будут отправляться через Bluetooth.';
      } catch (err) {
        elements.bluetoothStatus.textContent = 'Ошибка Bluetooth: ' + err.message;
      }
    }

    async function sendBluetooth(text) {
      if (!state.bluetoothCharacteristic) return;
      try {
        const encoder = new TextEncoder();
        await state.bluetoothCharacteristic.writeValue(encoder.encode(text));
      } catch (err) {
        elements.bluetoothStatus.textContent = 'Ошибка отправки Bluetooth: ' + err.message;
      }
    }

    function logout() {
      clearSession();
      setUserInfo(null);
      showScreen(false);
      elements.messages.innerHTML = '';
      setStatus('Offline', false);
    }

    loadSession();
    if (state.token) {
      setUserInfo(state.username);
      showScreen(true);
      startPolling();
    }

    elements.showLogin.addEventListener('click', () => { elements.showLogin.classList.add('active'); elements.showRegister.classList.remove('active'); elements.authButton.textContent = 'Войти'; elements.authMessage.textContent = ''; });
    elements.showRegister.addEventListener('click', () => { elements.showLogin.classList.remove('active'); elements.showRegister.classList.add('active'); elements.authButton.textContent = 'Зарегистрироваться'; elements.authMessage.textContent = ''; });
    elements.authButton.addEventListener('click', () => authAction(elements.showRegister.classList.contains('active')));
    elements.sendButton.addEventListener('click', sendMessage);
    elements.logoutButton.addEventListener('click', logout);
    elements.bluetoothButton.addEventListener('click', connectBluetooth);
    window.addEventListener('online', () => setStatus('Онлайн', true));
    window.addEventListener('offline', () => setStatus('Оффлайн', false));
  </script>
</body>
</html>'''


def load_users():
    global users
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as fh:
                users = json.load(fh)
        except Exception:
            users = {}
    else:
        users = {}


def save_users():
    with lock:
        with open(USERS_FILE, 'w', encoding='utf-8') as fh:
            json.dump(users, fh, ensure_ascii=False, indent=2)


def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def create_token():
    return secrets.token_urlsafe(24)


def authorize():
    token = request.headers.get('X-Auth-Token') or request.args.get('token')
    if not token:
        return None
    return sessions.get(token)


def queue_message(username, message):
    pending_messages.setdefault(username, []).append(message)


@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    if not username or not password:
        return jsonify(success=False, message='Введите имя и пароль.'), 400

    if username in users:
        return jsonify(success=False, message='Имя уже занято.'), 400

    users[username] = {
        'password': hash_password(password),
        'created_at': datetime.now(timezone.utc).isoformat() + 'Z'
    }
    save_users()
    return jsonify(success=True, message='Регистрация успешна. Теперь войдите.'), 200


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    if not username or not password:
        return jsonify(success=False, message='Введите имя и пароль.'), 400

    user = users.get(username)
    if not user or user.get('password') != hash_password(password):
        return jsonify(success=False, message='Неверное имя или пароль.'), 401

    token = create_token()
    sessions[token] = username
    pending_messages.setdefault(username, [])
    return jsonify(success=True, message='Вход выполнен.', token=token), 200


@app.route('/api/message', methods=['POST'])
def send_message():
    username = authorize()
    if not username:
        return jsonify(success=False, message='Требуется авторизация.'), 401

    data = request.get_json() or {}
    text = (data.get('text') or '').strip()
    to = (data.get('to') or '').strip()
    if not text:
        return jsonify(success=False, message='Текст сообщения пуст.'), 400

    message = {
        'from': username,
        'to': to or 'Все',
        'text': text,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    }

    if not to:
        for user in users.keys():
            if user != username:
                queue_message(user, message)
    else:
        if to not in users:
            return jsonify(success=False, message='Пользователь не найден.'), 404
        queue_message(to, message)

    queue_message(username, message)
    return jsonify(success=True, message='Сообщение отправлено.'), 200


@app.route('/api/poll', methods=['GET'])
def poll():
    username = authorize()
    if not username:
        return jsonify(success=False, message='Требуется авторизация.'), 401

    messages = pending_messages.pop(username, [])
    pending_messages[username] = []
    return jsonify(success=True, messages=messages), 200


@app.route('/api/online', methods=['GET'])
def online():
    username = authorize()
    if not username:
        return jsonify(success=False, message='Требуется авторизация.'), 401
    active = list({user for user in sessions.values() if user in users})
    return jsonify(success=True, online=active), 200


if __name__ == '__main__':
    load_users()
    port = int(os.environ.get('PORT', 8000))
    print("\n" + "="*60)
    print("🚀 МЕССЕНДЖЕР ЗАПУЩЕН!")
    print("="*60)
    print(f"Откройте в браузере:")
    print(f"  • http://localhost:{port}")
    print(f"  • http://127.0.0.1:{port}")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=port, threaded=True, debug=False)
