import socket
import signal
import os
import errno
import sys
import time
from io import StringIO

class WSGIConcurrentServer(object):
    address_family = socket.AF_INET
    socket_type = socket.SOCK_STREAM
    request_queue_size = 1024

    def __init__(self, server_address):
        self.listen_socket = listen_socket= socket.socket(self.address_family, self.socket_type)
        # set up address for reuse
        listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # bind and activate listen socket
        listen_socket.bind(server_address)
        listen_socket.listen(self.request_queue_size)
        print(f'Serving HTTP on port: {port}')
        host, port = listen_socket.getsockname()[:2]
        self.server_name = socket.getfqdn(host)
        self.server_port = port
        self.headers_set = []
        self.headers_sent = []
        self.client_sock = None

    def set_application(self, application):
        self.application = application


    def handle_request(self, client_connection):
        self.request_data = request_data = client_connection.recv(1024)
        #prints formatted request data
        print(''.join(f'< {line}') for line in request_data.splitlines())

        self.parse_request(request_data)
        env = self.get_environment()

        #call application and get HTTP response body
        result = self.application(env, self.start_response)
        #send response back to client
        self.finish_response(result)

    def parse_request(self, text):
        request_line = text.splitlines()[0]
        request_line = request_line.rstrip('\r\n')
        #break down request into components
        (self.request_method, self.path, self.request_version) = request_line.split()


    def get_environment(self):
        environment = {}

        environment['wsgi.version']     = (1,0)
        environment['wsgi.url_scheme']  = 'http'
        environment['wsgi.input']       = StringIO(self.request_data)
        environment['wsgi.errors']      = sys.stderr
        environment['wsgi.multithread'] = False
        environment['wsgi.multiprocess']= False
        environment['wsgi.run_once']    = False
        environment['REQUEST_METHOD']   = self.request_method
        environment['PATH_INFO']        = self.path
        environment['SERVER_NAME']      = self.server_name
        environment['SERVER_PORT']      = str(self.server_port)
        return environment

    def write(self, data):
        if not self.headers_set:
            raise AssertionError("write() before start_response()")

        elif not self.headers_sent:
            # Before the first output, send the stored headers
            status, response_headers = self.headers_sent[:] = self.headers_set
            sys.stdout.write('Status: %s\r\n' % status)
            for header in response_headers:
                sys.stdout.write('%s: %s\r\n' % header)
            sys.stdout.write('\r\n')

        sys.stdout.write(data)
        sys.stdout.flush()


    def start_response(self, status, response_headers, exc_info=None):
        server_headers = [('Date', time.now()),('Server','WSGIServer 0.2')]
        if exc_info:
            try:
                if self.headers_sent:
                    # Re-raise original exception if headers sent
                    raise exc_info[0](exc_info[1]).with_traceback(exc_info[2])
            finally:
                exc_info = None  # avoid dangling circular ref
        elif self.headers_set:
            raise AssertionError("Headers already set!")

        self.headers_set[:] = [status, response_headers + server_headers]
        return self.write


    def finish_response(self, result):
        try:
            status, response_headers= self.headers_set
            response = f'HTTP/1.1 {status}\r\n'
            for header in response_headers:
                response += f'{header[0]}: {header[1]}\r\n'
            response += '\r\n'
            for data in result:
                response += data
            print(''.join(f'> {line}\n' for line in response.splitlines()))
            self.client_sock.sendall(response)
        finally:
            self.client_sock.close()


    def serve_server(self):
        client = self.listen_socket
        while True:
            try:
                self.client_sock, client_address = client.accept()
            except IOError as e:
                code, msg = e.args
                if code == errno.EINTR:
                    #restarts accept if interruption occurs
                    continue
                else:
                    raise
            pid = os.fork()
            if pid == 0: #child process
                client.close() #close child
                self.handle_request(self.client_sock)
                self.client_sock.close()
                os._exit(0)
            else: #parent process
                self.client_sock.close() #close parent and begin loop again

server_address = (host, port) = '', 8080


def zombie_killer(signum, frame):
    while True:
        try:
            # wait for child process (-1), do not block and return EWOULDBLOCK error(os.WNOHANG)
            pid, status = os.waitpid(-1, os.WNOHANG)
            print(f'Child {pid} terminated with status {status}')
        except OSError:
            return
        if pid == 0:
            return


def make_server(server_address, application):
    signal.signal(signal.SIGCHLD, zombie_killer)
    server = WSGIConcurrentServer(server_address)
    server.set_application(application)
    return server

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('Provide a WSGI application object as module:callable')
    app_path = sys.argv[1]
    module, application = app_path.split(':')
    module = __import__(module)
    application = getattr(module, application)
    httpd = make_server(server_address, application)
    print('WSGIServer: Serving HTTP on port {port} ...\n'.format(port=port))
    httpd.serve_server()
