import json, socket, selectors
from collections import defaultdict

class BaseServer:
    def __init__(self, ip: str="127.0.0.1", port: int=8080) -> None:
        self.state: dict = {
            "running": False
        }
        self.encoding: str = "utf-8"
        self.address: tuple[str, int] = (ip, port)
        self.methods: dict = defaultdict(dict)
        self.connections: dict = defaultdict(dict)
        self.selector: selectors.DefaultSelector = selectors.DefaultSelector()
        self.endpoint: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Automatically register methods marked with @server_method
        self._auto_register_methods()

    def log_stdout(self, message: str) -> None:
        print(f"[server-log] | {message}\n")

    """ server state """
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

    """ server I/O """
    def _build_response(self, method: str, params: list|dict) -> dict:
        return {"jsonrpc": "2.0", "method": method, "params": params}

    def _has_responses(self, address: tuple[str, int]) -> bool:
        try:
            if not self.connections[address]["responses"]:
                self.selector.modify(
                    self.connections[address]["endpoint"],
                    selectors.EVENT_READ,
                    self._service_connection
                )
                return False
            return True
        except KeyError as e:
            self.log_stdout(f"endpoint address not found: {address}")
            return False

    def queue_response(self, address: tuple[str, int], response: dict) -> None:
        try:
            self.connections[address]["responses"].append(response)
            self.selector.modify(
                    self.connections[address]["endpoint"],
                    selectors.EVENT_READ | selectors.EVENT_WRITE,
                    self._service_connection
                )
        except KeyError as e:
            self.log_stdout(f"endpoint address not found: {address}")
    
    def dequeue_response(self, address: tuple[str, int]) -> None:
        try:
            return self.connections[address]["responses"].pop(0)
        except KeyError as e:
            self.log_stdout(f"endpoint address not found: {address}")
            return {"NONE"}

    def _read(self, endpoint: socket.socket) -> None:
        try:
            address = endpoint.getpeername()
            request = json.loads(endpoint.recv(1024).decode(self.encoding))
            request["params"] = json.loads(request["params"])   # de-serialize parameters incase of object-params
            if request:
                self.log_stdout(f"request: {request} ({len(request)} bytes)")
                self.on_read(endpoint, request)
        except Exception as e: self.log_stdout(f"server read exception: {e}")

    def _write(self, endpoint: socket.socket) -> int:
        try:
            sent = 0
            address = endpoint.getpeername()
            response = self.dequeue_response(address)
            encoded = json.dumps(response).encode(self.encoding)
            while sent < len(encoded):
                sent += endpoint.send(encoded[sent:1024])
            self.log_stdout(f"response: {response}({sent} bytes)")
            self.on_write(endpoint, response)
        except Exception as e:
            self.log_stdout(f"client write exception: {e}")
            return 0

    """ server methods """
    def _auto_register_methods(self):
        """Automatically registers all methods decorated with @server_method."""
        for name in dir(self):
            attr = getattr(self, name)
            if callable(attr) and getattr(attr, "_is_server_method", False):
                self.register_method(name, attr)

    @staticmethod
    def server_method(func):
        """this decorator marks a method for automatic registration in the BaseServer."""
        func._is_server_method = True
        return func

    def register_method(self, name: str, callback) -> None:
        try:
            if name not in self.methods:
                self.methods[name] = callback
                self.log_stdout(f"server method registered: {name}")
        except Exception as e: self.log_stdout(f"failed to register method: {name} | {e}")

    def unregister_method(self, name: str) -> None:
        try:
            if self.methods.get(name, False) != False:
                self.methods.pop(name)
                self.log_stdout(f"server method unregistered: {name}")
        except KeyError as e: self.log_stdout(f"method not found: {name}")
        except Exception as e: self.log_stdout(f"failed to unregister method: {name} | {e}")

    """ internal server API """
    def _handle_connection(self, endpoint: socket.socket, mask: int) -> None:
        client, address = endpoint.accept()
        if client is not None:
            self.log_stdout(f"incoming connection: {address}")
            
            client.setblocking(False)
            self.connections[address] = {
                "responses": [],
                "endpoint": client
            }
            
            self.selector.register(
                client,
                selectors.EVENT_READ,
                self._service_connection
            )
            
            self.on_connect(client)
            self.log_stdout(f"incoming connection: {address}")

    def _service_connection(self, endpoint: socket.socket, mask: int) -> None:
        address = endpoint.getpeername()
        if (mask & selectors.EVENT_READ) == selectors.EVENT_READ:
            self._read(endpoint)
        
        if (mask & selectors.EVENT_WRITE) == selectors.EVENT_WRITE:
            if self._has_responses(address):
                self._write(endpoint)

    def _handle_disconnect(self, endpoint: socket.socket) -> None:
        try:
            address = endpoint.getpeername()
            self.connections.pop(address)
            self.selector.unregister(endpoint)
            endpoint.close()
            self.on_disconnect(endpoint)
            self.log_stdout(f"disconnected: {address}")
        except Exception as e: self.log_stdout(f"failed to gracefully disconnect: {address} | {e}")

    """ external server API """
    def start(self) -> None:
        if self.get_state("running") == False:
            self.endpoint.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # allows server socket to be 're-bound'
            self.endpoint.setblocking(False)
            self.endpoint.bind(self.address)
            self.endpoint.listen()
            self.selector.register(
                self.endpoint,
                selectors.EVENT_READ,
                self._handle_connection
            )
            self.set_state("running", True)
            self.log_stdout(f"server started at: {self.address}")

    def run(self) -> None:
        while self.get_state("running") == True:
            selection = self.selector.select(timeout=None)
            for key, mask in selection:
                if callable(key.data):
                    callback = key.data
                    endpoint = key.fileobj
                    callback(endpoint, mask)   # handle/service_connection() callback
                else: break
    
    def stop(self) -> None:
        try:
            self.set_state("running", False)
            for address in self.connections:
                endpoint = self.connections[address]["endpoint"]
                endpoint.close()
            del self.methods
            del self.connections
            self.selector.close()
            self.endpoint.close()
        except Exception as e: self.log_stdout(f"failed to gracefully shutdown")

    """ server hooks """
    def on_read(self, endpoint: socket.socket, request: dict):
        """
        a subclassed `BaseServer` should implement this callback
        to provide a layer of custom logic after a server read is complete.
        
        a subclassed `BaseServer` can still call the superclass's implementation,
        as by default this method is used for parsing the request and calling corresponding server methods.
        
        @param: endpoint
            - the endpoint read from
        
        @param: request
            - the request read
        """
        try:
            if self.methods.get(request["method"], False) != False:
                method = self.methods[request["method"]]
                if callable(method):
                    method(endpoint, request)
                    self.log_stdout(f"server method called: {request["method"]}")
            else: 
                self.queue_response(endpoint.getpeername(), self._build_response("error", f"invalid server method: {request["method"]}"))
                self.log_stdout(f"invalid server method call from: {endpoint.getpeername()} | {request["method"]}")
        except KeyError as e:
            self.queue_response(endpoint.getpeername(), self._build_response("error", f"invalid server method: {request["method"]}"))
            self.log_stdout(f"invalid server method call from: {endpoint.getpeername()} | {request["method"]}")

    def on_write(self, endpoint: socket.socket, response: dict):
        """
        a subclassed `BaseServer` should implement this callback
        to provide a layer of custom logic after a server write is complete

        by default, this method does nothing.

        @param: endpoint
            - the endpoint written to
        
        @param: response
            - the response written
        """

    def on_connect(self, endpoint: socket.socket):
        """
        this method is a no-op default. a `BaseServer` subclass must implement
        this method for extended server-side logic
        """

    def on_disconnect(self, endpoint: socket.socket):
        """
        this method is a no-op default. a `BaseServer` subclass must implement
        this method for extended server-side logic
        """
