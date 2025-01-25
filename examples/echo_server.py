import d34dnet as dnet

class EchoServer(dnet.inet.BaseServer):
    def __init__(self, ip = "127.0.0.1", port = 8080):
        super().__init__(ip, port)

    def on_read(self, transport, request):
        if request.get("method") == "echo":
            self.queue_response(transport.getpeername(), request)

s = EchoServer()
s.start()
s.run()

# if __name__ == "__main__":
#     class MyServer(dnet.inet.BaseServer):
#         @dnet.inet.BaseServer.server_method
#         def echo(self, transport, request):
#             self.queue_response(transport.getpeername(), request)

#         @dnet.inet.BaseServer.server_method
#         def disconnect(self, transport, request):
#             self._handle_disconnect(transport)

#     server = MyServer()
#     server.start()
#     server.run()
#     server.stop()
