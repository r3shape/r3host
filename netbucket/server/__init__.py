import json, socket, selectors
from collections import defaultdict

class NBserver:
    def __init__(self, name: str, ip="127.0.0.1", port=8000) -> None:
        self.name: str = name
        self.codec: str = "utf-8"
        self.running: bool = False
        self.queue_size: int = 1024
        self.buffer_size: int = 1024

        self.command_prefix: str = "/"
        self.commandarg_prefix: str = "|"
        self.command_delimiter: str = "\\"
        self.command_register: dict[str, callable] = {}

        self.ip: str = ip
        self.port: int = port
        self.address: tuple[str, int] = (ip, port)
        self.selector: selectors.DefaultSelector = selectors.DefaultSelector()
        self.message_queues: dict[socket.socket, list[str]] = defaultdict(list)
        self.socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def log_stdout(self, message: str) -> None:
        print(f"[ARSERVER-LOG] {self.name} | {message}\n")

    def dump(self) -> dict:
        return {
            "ip": self.ip,
            "port": self.port,
            "name": self.name,
            "codec": self.codec,
            "buffer_size": self.buffer_size,
            "command_prefix": self.command_prefix,
            "commandarg_prefix": self.commandarg_prefix,
            "command_delimiter": self.command_delimiter,
        }

    def dumps(self) -> str:
        return self.dump().__str__()

    def register_command(self, command: str, callback: callable) -> None:
        if self.command_register.get(command, False) == False:
            self.command_register[command] = callback
            self.log_stdout(f"command registered: {command}")
    
    def query_command(self, command: str) -> callable:
        callback = None
        if self.command_register.get(command, False) != False:
            callback = self.command_register[command]
        return callback

    def unregister_command(self, command: str) -> None:
        if self.command_register.get(command, False) != False:
            callback = self.command_register.pop(command)
            self.log_stdout(f"command unregistered: {command}")

    def startup(self) -> None:
        self.log_stdout(f"starting: {self.ip}:{self.port}")
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # allows server socket to be 're-bound'
        self.socket.bind((self.ip, self.port))
        self.socket.setblocking(False)
        self.socket.listen()
        self.selector.register(
            self.socket,
            selectors.EVENT_READ,
            self.handle_connection
        )
        self.running = True
        self.log_stdout(f"started: {self.ip}:{self.port}")

    def build_message(self, message: str) -> dict:
        try:
            built = {"command": None, "payload": None}
            if message.startswith(self.command_prefix):
                if message.__contains__(self.command_delimiter):
                    built["command"], built["payload"] = map(str.strip, message[1:].split(self.command_delimiter))
                else:   # no command delimiter, we assume the entire message is the command!
                    built["command"] = message[1:].strip()
            else:
                built["payload"] = message
            return built
        except Exception as e: self.log_stdout(f"exception: {e}")

    def read_message(self, client_socket: socket.socket) -> dict:
        try:
            message: dict = json.loads(client_socket.recv(self.buffer_size).decode(self.codec))
            if message:
                self.log_stdout(f"message read: {message}")
                return message
            return {"command": None, "payload": None}
        except Exception as e:
            self.log_stdout(f"read exception: {e}")
            return {"command": None, "payload": None}

    def write_message(self, client_socket: socket.socket, message: dict) -> int:
        try:
            sent = 0
            encoded = json.dumps(message).encode(self.codec)
            while sent < len(message):
                sent += client_socket.send(encoded[sent:self.buffer_size])
            self.log_stdout(f"message written: '{message}({sent}bytes)'")
            return sent
        except Exception as e:
            self.log_stdout(f"write Exception: {e}")
            return 0

    def shout_message(self, client_socket: socket.socket, message: str) -> None:
        try:
            address = client_socket.getpeername() 
            for client in self.message_queues.keys():
                if client != client_socket:
                    self.queue_message(client, f"[SHOUT] from ({address[0]}, {address[1]}): {message}")
        except Exception as e: self.log_stdout(f"broadcast message exception: {e}")

    def check_messages(self, client_socket: socket.socket) -> bool:
        try:
            if not self.message_queues[client_socket]:  # no more messages to send this client
                self.selector.modify(
                    client_socket,
                    selectors.EVENT_READ,
                    self.handle_client
                )
                return False
            return True
        except Exception as e:
            self.log_stdout(f"check message Exception: {e}")

    def get_message(self, client_socket: socket.socket) -> str:
        try:
            if self.message_queues[client_socket]:
                # send a response from the message queue
                return self.message_queues[client_socket].pop(0)
        except Exception as e:
            self.log_stdout(f"get message Exception: {e}")
            return ""

    def queue_message(self, client_socket: socket.socket, message: str) -> None:
        try:
            self.message_queues[client_socket].append(message)
            self.selector.modify(
                client_socket,
                selectors.EVENT_READ | selectors.EVENT_WRITE,
                self.handle_client
            )
        except Exception as e: self.log_stdout(f"queue message exception: {e}")

    def parse_message(self, client_socket: socket.socket, message: dict) -> None:
        commandargs = None
        command = message["command"]
        payload = message["payload"]

        if command:
            # extract command arguments
            if command.__contains__(self.commandarg_prefix):
                parts = command.split(self.commandarg_prefix)
                command = parts[0]
                commandargs = parts[1:]
                self.log_stdout(f"command arguments supplied: {commandargs}")

            # handle default commands
            if command == "sd":
                self.shutdown()
                return
            if command == "dc":
                self.handle_disconnection(client_socket)
                return
            if command == "list":
                client_list = ", ".join(str(s.getpeername()) for s in list(self.message_queues.keys()))
                self.queue_message(client_socket, f"connected: {client_list}")
                return
            if command == "shout":
                self.shout_message(client_socket, payload)
                return

            # query and call registered non-default callbacks
            try:
                callback = self.query_command(command)
                if callable(callback): callback(payload)
            except Exception as e: self.log_stdout(f"callback exception: {e}")
        else:
            # server "default behavior" is to echo
            self.queue_message(client_socket, f"echo: {message}")

    def handle_connection(self, server_socket: socket.socket, mask: int) -> None:
        client_socket, client_address = server_socket.accept()
        client_socket.setblocking(False)
        self.message_queues[client_socket] = []
        self.selector.register(client_socket, selectors.EVENT_READ, self.handle_client)
        
        # recv client info
        client_info = json.loads(client_socket.recv(self.buffer_size).decode(self.codec))
        self.log_stdout(f"client info: {client_info}")
        
        # send over current server info
        client_socket.sendall(json.dumps(self.dump()).encode(self.codec))

        self.log_stdout(f"connected: {client_address}")
    
    def handle_disconnection(self, client_socket: socket.socket) -> None:
        address = client_socket.getpeername()
        self.message_queues.pop(client_socket, None)  # remove the message queue
        self.selector.unregister(client_socket)
        client_socket.close()
        self.log_stdout(f"disconnected: {address}")

    def handle_client(self, client_socket: socket.socket, mask: int) -> None:
        try:
            if mask & selectors.EVENT_READ:  # read events
                message = self.read_message(client_socket)
                self.parse_message(client_socket, message)

            if mask & selectors.EVENT_WRITE:  # write events
                if self.check_messages(client_socket):
                    message = self.get_message(client_socket)
                    self.write_message(client_socket, message)
        except Exception as e:
            self.log_stdout(f"handle client exception: {e}")
            self.handle_disconnection(client_socket)

    def run(self) -> None:
        while self.running:
            try:
                selection = self.selector.select(timeout=None)  # a blocking call
                for key, mask in selection:
                    callback = key.data  # the callback function to handle this selection
                    callback(key.fileobj, mask)
            except Exception as e: self.log_stdout(f"run exception: {e}")

    def shutdown(self) -> None:
        self.log_stdout("shutting down")
        for client in list(self.message_queues.keys()):
            self.handle_disconnection(client)
        self.selector.close()
        self.socket.close()
        self.running = False
        self.log_stdout("shut down")


if __name__ == "__main__":
    server = NBserver("The Server")

    def scream_callback(payload: str) -> None:
        server.log_stdout("SCREAMING CALLBACK")
    server.register_command("SCREAM", scream_callback)

    server.startup()
    server.run()
    server.shutdown()
