import json, socket, threading

class NBclient:
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.running: bool = True
        self.connected: bool = False
        self.address: tuple[str, int] = None
        self.thread_lock: threading.Lock = threading.Lock()
        self.read_thread: threading.Thread = None   # NBclient is dual-threaded leaving writes to block the main thread
        self.socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # allows client socket to be 're-bound'
        
        # server info (set to defaults but updated on successful connection)
        self.codec: str = "utf-8"
        self.buffer_size: int = 1024
        self.server_name: str = None
        self.command_prefix: str = None
        self.commandarg_prefix: str = None
        self.command_delimiter: str = None
        self.server_address: tuple[str, int] = None

    def dump(self) -> dict:
        return {
            "name": self.name,
            "ip": self.address[0],
            "port": self.address[1]
        }
    
    def dumps(self) -> str:
        return self.dump().__str__()

    def log_stdout(self, message: str) -> None:
        print(f"[NBCLIENT-LOG] {self.name} | {message}\n")

    def build_message(self, message: str) -> dict:
        if self.connected:
            built = {"command": None, "payload": None}
            if message.startswith(self.command_prefix):
                if message.__contains__(self.command_delimiter):
                    built["command"], built["payload"] = map(str.strip, message[1:].split(self.command_delimiter))
                else:   # no command delimiter, we assume the entire message is the command!
                    built["command"] = message[1:].strip()
            else:
                built["payload"] = message
            return built

    def read_message(self) -> None:
        while self.connected:
            try:
                message: dict = json.loads(self.socket.recv(self.buffer_size).decode(self.codec))
                if message: self.log_stdout(f"message read: {message}")
            except Exception as e: self.log_stdout(f"read exception: {e}")

    def write_message(self, message: dict) -> int:
        if self.connected:
            try:
                sent = 0
                encoded = json.dumps(message).encode(self.codec)
                while sent < len(message):
                    sent += self.socket.send(encoded[sent:self.buffer_size])
                self.log_stdout(f"message written: '{message}({sent}bytes)'")
                return sent
            except Exception as e:
                self.log_stdout(f"write Exception: {e}")
                return 0

    def connect(self, ip: str="127.0.0.1", port: int=8000) -> None:
        if not self.connected:
            try:
                self.server_address = (ip, port)
                self.socket.connect(self.server_address)
                self.address = self.socket.getsockname()

                # send client info
                self.socket.sendall(json.dumps(self.dump()).encode(self.codec))

                # recv server info
                server_info = json.loads(self.socket.recv(self.buffer_size).decode(self.codec))
                with self.thread_lock:
                    self.codec = server_info["codec"]
                    self.server_name = server_info["name"]
                    self.buffer_size = server_info["buffer_size"]
                    self.command_prefix = server_info["command_prefix"]
                    self.commandarg_prefix = server_info["commandarg_prefix"]
                    self.command_delimiter = server_info["command_delimiter"]

                    self.log_stdout(f"server info: {server_info}")

                    self.connected = True

                self.read_thread = threading.Thread(target=self.read_message, daemon=True)
                self.read_thread.start()
                
                self.log_stdout(f"connected: {self.server_address}")
            except Exception as e: self.log_stdout(f"exception: {e}")

    def reconnect(self) -> None:
        try:
            if self.connected:
                self.log_stdout(f"reconnecting...")
                
                address = self.server_address
                self.disconnect()

                self.connect(address[0], address[1])
                self.log_stdout(f"reconnected...")
        except Exception as e:
            self.log_stdout(f"reconnect exception: {e}")

    def disconnect(self) -> None:
        if self.connected:
            try:
                address = self.server_address
                self.log_stdout(f"disconnecting: {address}")

                with self.thread_lock:
                    self.connected = False

                self.socket.close()
                self.read_thread.join(timeout=2.0)
                
                self.address = None
                self.server_address = None
                
                self.log_stdout(f"disconnected: {address}")
            except Exception as e: self.log_stdout(f"exception: {e}")

    def run(self) -> None:
        try:
            while self.running:
                if self.connected:
                    raw_message = input(">: ").strip()
                    if raw_message: self.write_message(self.build_message(raw_message))
        except Exception as e: self.log_stdout(f"run exception: {e}")

    def shutdown(self) -> None:
        if self.running:
            self.log_stdout("shutting down")
            self.disconnect()
            self.running = False
            self.log_stdout("shut down")

if __name__ == "__main__":
    client = NBclient("mikeman123")
    client.connect()
    client.run()
    client.shutdown()
