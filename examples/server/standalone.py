import d34dnet as dnet

s = dnet.inet.BaseServer()
s.register_method("dc", lambda t, r: s._handle_disconnect(t))
s.register_method("echo", lambda t, r: s.queue_response(t.getpeername(), r))
s.start()
s.run()
s.stop()
