import r3host as dnet

class MyServer(dnet.inet.BaseServer):
    @dnet.inet.BaseServer.server_method
    def echo(self, endpoint, request):
        self.queue_response(endpoint.getpeername(), request)

    @dnet.inet.BaseServer.server_method
    def disconnect(self, endpoint, request):
        self._handle_disconnect(endpoint)

server = MyServer()
server.start()
server.run()
server.stop()
