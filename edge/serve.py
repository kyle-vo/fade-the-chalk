"""Serve output/ on http://localhost:8765 (for previewing board.html)."""
import os, sys, http.server, functools
d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
print("serving", d, "on", port, flush=True)
http.server.ThreadingHTTPServer(('127.0.0.1', port), functools.partial(http.server.SimpleHTTPRequestHandler, directory=d)).serve_forever()
