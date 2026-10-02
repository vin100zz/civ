// WebSocket link to the server, with automatic reconnection.

let socket = null;
let onMessage = () => {};
let onStatus = () => {};

export function connect(messageHandler, statusHandler) {
  onMessage = messageHandler;
  onStatus = statusHandler;
  open();
}

function open() {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  socket = new WebSocket(`${scheme}://${location.host}/ws`);
  socket.onopen = () => onStatus(true);
  socket.onmessage = (event) => onMessage(JSON.parse(event.data));
  socket.onclose = () => {
    onStatus(false);
    setTimeout(open, 2000);
  };
}

export function send(command) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(command));
}
