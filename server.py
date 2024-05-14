from http.server import SimpleHTTPRequestHandler, HTTPServer
from common import SERVER_HOST, SERVER_PORT, get_cmd_output, get_protocol, CERT_FILE, KEY_FILE
import time
import threading
import sys
from workflow import Workflow, ICON_WEB, ICON_NOTE, ICON_BURN, ICON_SWITCH, ICON_HOME, ICON_COLOR, ICON_INFO, ICON_SYNC, web, PasswordNotFound
from urllib.parse import urlparse, parse_qs
import ssl
import os.path

def ensure_keys(certfile, keyfile, wf):
    if not (os.path.exists(certfile) and os.path.exists(keyfile)):
        get_cmd_output(f"openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout '{keyfile}' -out '{certfile}' -config ssl.cnf", wf)
    
def get_ssl_context(certfile, keyfile, wf):
    certfile = wf.datafile(certfile)
    keyfile = wf.datafile(keyfile)
    ensure_keys(certfile, keyfile, wf)
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    context.load_cert_chain(certfile, keyfile)
    #context.set_ciphers("@SECLEVEL=1:ALL")
    return context

def kill_server(request):
    threading.Thread(target=webServer.server_close).start()
    
routes = {
    '/link.html' : 'file',
    '/oauth.html' : 'file',
    '/images/wallpaper.jpg' : 'file',
    '/images/alfred-plaid.png' : 'file',
    '/kill': kill_server
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
    if 'https' == get_protocol(wf): 
        context = get_ssl_context(CERT_FILE, KEY_FILE, wf)
        webServer.socket = context.wrap_socket(webServer.socket, server_side=True)

    wf.logger.debug("Server started https://%s:%s" % (SERVER_HOST, SERVER_PORT))
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