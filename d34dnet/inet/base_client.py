import os, signal, json, socket, threading

class BaseClient:
    def __init__(self):
        self.state: dict = {
            "connected": False,
            "log-stdout": True,
        }
        self.encoding: str = "utf-8"
        self.address: tuple[str, int] = None
        self.read_thread: threading.Thread = None
        self.thread_lock: threading.Lock = threading.Lock()
        self.endpoint: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def log_stdout(self, message: str) -> None:
        if self.state["log-stdout"] == True:
            print(f"[client-log] | {message}\n")

    """ client state """
    def get_state(self, state_key: str):
        try:
            return self.state.get(state_key, None)
        except KeyError as e:
            self.log_stdout(f"state key not found: {state_key}")
            return None
   
    def set_state(self, state_key: str, value):
        try:
            self.state[state_key] = value
        except KeyError as e:
            self.log_stdout(f"state key not found: {state_key}")
            return

    """ client I/O """
    def build_request(self, method: str, params: list|dict) -> dict:
        return {"jsonrpc": "2.0", "method": method, "params": json.dumps(params)}    # serialize request parameters in case of object-params

    def _read(self) -> None:
        if self.get_state("connected") == True:
            while self.get_state("connected") == True:
                try:
                    response = json.loads(self.endpoint.recv(1024).decode(self.encoding))
                    response["params"] = json.loads(response["params"])   # de-serialize parameters incase of object-params
                    if response:
                        self.log_stdout(f"response recv: {response}")
                        self.on_read(response)
                except (json.JSONDecodeError, ConnectionError) as e:
                    self.log_stdout(f"connection error: {self.address}")
                    self.disconnect()
                except KeyboardInterrupt:
                    self.disconnect()
                except Exception as e:
                    self.log_stdout(f"client read exception: {e}")
                    self.disconnect()

    def write(self, request: dict) -> int:
        if self.get_state("connected") == True:
            try:
                sent = 0
                encoded = json.dumps(request).encode(self.encoding)
                while sent < len(encoded):
                    sent += self.endpoint.send(encoded[sent:1024])
                self.on_write(request)
                return sent
            except ConnectionError as e:
                self.log_stdout(f"connection error: {self.address}")
                self.disconnect()
            except Exception as e:
                self.log_stdout(f"client write exception: {e}")
                return 0

    """ external client API """
    def connect(self, ip: str="127.0.0.1", port: int=8080) -> None:
        if self.get_state("connected") == False:
            try:
                self.address = (ip, port)
                self.endpoint.connect(self.address)
                self.read_tread = threading.Thread(target=self._read, daemon=True)
                self.set_state("connected", True)
                self.read_tread.start()
                self.on_connect()
                self.log_stdout(f"connected to: {self.address}")
            except ConnectionError as e:
                self.log_stdout(f"connection failed: {self.address}")
    
    def reconnect(self):
        if self.address:
            try:
                self.connect(*self.address)
            except Exception as e:
                self.log_stdout(f"reconnection failed: {e}")

    def disconnect(self) -> None:
        try:
            if self.get_state("connected") == True:
                self.on_disconnect()
                self.set_state("connected", False)
                self.read_tread.join(timeout=1.0)
                self.endpoint.close()
                self.log_stdout(f"disconnected from: {self.address}")
        except (RuntimeError, RuntimeWarning) as e:
            self.log_stdout(f"runtime error: {e}")
            self.endpoint.close()
            self.set_state("connected", False)
            self.log_stdout(f"disconnected from: {self.address}")
        finally: os.kill(os.getpid(), signal.SIGINT)

    def run(self) -> None:
        while self.get_state("connected") == True:
            try:
                method = input("(request method) >: ")
                params = input("(request params) >: ")
                request = self.build_request(method, params)
                if request: self.write(request)
            except KeyboardInterrupt:
                self.disconnect()
            except Exception as e:
                self.log_stdout(f"client runtime exception: {e}")
                self.disconnect()

    """ client hooks """
    def on_read(self, response: dict) -> None:
        """
        this method is a no-op default. a `BaseClient` subclass must implement
        this method for extended client-side logic
        """

    def on_write(self, request: dict) -> None:
        """
        this method is a no-op default. a `BaseClient` subclass must implement
        this method for extended client-side logic
        """

    def on_connect(self) -> None:
        """
        this method is a no-op default. a `BaseClient` subclass must implement
        this method for extended client-side logic
        """

    def on_disconnect(self) -> None:
        """
        this method is a no-op default. a `BaseClient` subclass must implement
        this method for extended client-side logic
        """
