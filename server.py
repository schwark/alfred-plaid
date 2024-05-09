from http.server import SimpleHTTPRequestHandler, HTTPServer
from common import SERVER_HOST, SERVER_PORT
import time
import threading
import sys
from workflow import Workflow, ICON_WEB, ICON_NOTE, ICON_BURN, ICON_SWITCH, ICON_HOME, ICON_COLOR, ICON_INFO, ICON_SYNC, web, PasswordNotFound
from urllib.parse import urlparse, parse_qs

def kill_server(request):
    threading.Thread(target=webServer.server_close).start()
    
def pub_token(request):
    wf = Workflow(libraries=['./lib'], update_settings={
        'github_slug': 'schwark/alfred-plaid'
    })
    params = parse_qs(urlparse(request.path).query)
    if 'pubtoken' in params:
        pass

routes = {
    '/link.html' : 'file',
    '/kill': kill_server,
    '/pubtoken': pub_token
}

webServer = None

def log(text):
    sys.stderr.write(f"{text}\n")

class MyServer(SimpleHTTPRequestHandler):
    def do_GET(self):
        parts = self.path.split('?')
        path = parts[0]
        log(f'path is {path}')
        query = parts[1] if len(parts) > 1 else None
        if(path in routes):
            log(f'path in routes and route is {routes[path]}')
            if(callable(routes[path])):
                routes[path](self)
            elif('file' == routes[path]):
                self.path = path
                return SimpleHTTPRequestHandler.do_GET(self)
            else:
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(bytes("<html><head><title>https://pythonbasics.org</title></head>", "utf-8"))
                self.wfile.write(bytes("<p>Request: %s</p>" % self.path, "utf-8"))
                self.wfile.write(bytes("<body>", "utf-8"))
                self.wfile.write(bytes("<p>This is an example web server.</p>", "utf-8"))
                self.wfile.write(bytes("</body></html>", "utf-8"))

def run_server(wf):
    webServer = HTTPServer((SERVER_HOST, SERVER_PORT), MyServer)

    wf.logger.debug("Server started http://%s:%s" % (SERVER_HOST, SERVER_PORT))
    try:
        threading.Thread(target=webServer.serve_forever, daemon=True).start()
    except KeyboardInterrupt:
        stop_server(wf)

def stop_server(wf):
    try:
        webServer.server_close()
        wf.logger.debug("Server stopped.")
    except Exception:
        pass

if __name__ == "__main__":
    pass