"""Bounded opaque TCP ingress to one helper-inspected numeric fixture peer."""
import argparse
import ipaddress
import select
import signal
import socket
import socketserver
import threading
import time

MAX_CONNECTIONS = 8
BUFFER_BYTES = 65536
MAX_TRANSFER_BYTES = 32 * 1024 * 1024
TOTAL_SECONDS = 150


class RelayServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = False
    block_on_close = True
    request_queue_size = MAX_CONNECTIONS

    def __init__(self, address, peer, port):
        # No DNS or URL routing. The launcher supplies the inspected app IP.
        ipaddress.ip_address(peer)
        if not 0 < port <= 65535 or port == 8765:
            raise ValueError('invalid fixture relay port')
        self.peer = (peer, port)
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.sockets = set(); self.lock = threading.Lock()
        super().__init__(address, RelayHandler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request); return
        with self.lock: self.sockets.add(request)
        try: super().process_request(request, address)
        except BaseException:
            self.slots.release(); raise

    def process_request_thread(self, request, address):
        try: super().process_request_thread(request, address)
        finally:
            with self.lock: self.sockets.discard(request)
            self.slots.release()

    def handle_error(self, request, address):
        pass  # Never log traffic, headers, credentials or exceptions.

    def close_connections(self):
        with self.lock:
            for connection in self.sockets:
                try: connection.shutdown(socket.SHUT_RDWR)
                except OSError: pass


class RelayHandler(socketserver.BaseRequestHandler):
    def handle(self):
        upstream = None
        try:
            upstream = socket.create_connection(self.server.peer, timeout=5)
            sockets = (self.request, upstream)
            for connection in sockets: connection.setblocking(False)
            outgoing = {connection:bytearray() for connection in sockets}
            reading = set(sockets); write_closed = set()
            deadline = time.monotonic()+TOTAL_SECONDS; transferred = 0
            while time.monotonic() < deadline:
                for source, destination in ((sockets[0],sockets[1]),(sockets[1],sockets[0])):
                    if source not in reading and not outgoing[destination] and destination not in write_closed:
                        destination.shutdown(socket.SHUT_WR); write_closed.add(destination)
                if not reading and not any(outgoing.values()): return
                readable=[s for s in reading if len(outgoing[sockets[1] if s is sockets[0] else sockets[0]]) < BUFFER_BYTES]
                writable=[s for s in sockets if outgoing[s]]
                ready_read,ready_write,_=select.select(readable,writable,[],min(.2,max(0,deadline-time.monotonic())))
                for connection in ready_write:
                    sent=connection.send(outgoing[connection]); del outgoing[connection][:sent]
                for source in ready_read:
                    destination=sockets[1] if source is sockets[0] else sockets[0]
                    data=source.recv(min(16384,BUFFER_BYTES-len(outgoing[destination])))
                    if not data: reading.remove(source); continue
                    transferred+=len(data)
                    if transferred>MAX_TRANSFER_BYTES: return
                    outgoing[destination].extend(data)
        except OSError:
            pass
        finally:
            if upstream is not None: upstream.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--peer',required=True)
    parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args()
    stop=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,lambda *_:stop.set())
    with RelayServer(('0.0.0.0',args.port),args.peer,args.port) as server:
        worker=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05}); worker.start()
        try: stop.wait()
        finally: server.shutdown(); server.close_connections(); worker.join(5)


if __name__=='__main__': main()
