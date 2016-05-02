# based on https://github.com/flowroute/jsonrpc-ns

import socket
import socks
import ssl
import json
import traceback
import logging
from copy import copy


def request(addr, method, data, timeout=None):
    '''Simple single function interface
    for JSON-RPC request that
    creates and destroys a socket for every request.
    '''
    host, port = addr.split(':')
    jsrpc = JSONRPCProxy(host, port, connect_timeout=timeout)
    r = jsrpc.request(method, data, timeout=timeout)
    jsrpc.close()
    return r


def notify(addr, method, data):
    '''Simple single function interface
    for JSON-RPC notify that
    creates and destroys a socket for every request.
    '''
    host, port = addr.split(':')
    jsrpc = JSONRPCProxy(host, port)
    r = jsrpc.notify(method, data)
    jsrpc.close()
    return r

def balanced(txt):
    if txt=='':
        return False
    braced = 0
    for ch in txt:
        if ch == '{': braced += 1
        if ch == '}':
            braced -= 1
            if braced < 0: return False
    return braced == 0

class JSONRPCError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class JSONRPCBadResponse(JSONRPCError):
    pass


class JSONRPCRequestFailure(JSONRPCError):
    pass


class JSONRPCResponseError(JSONRPCError):
    '''
    JSONRPCResponseError contains a dictionary with a code and a message
    '''
    pass


class JSONRPCProxy:

    def __init__(self, host, port, version='2.0', connect_timeout=10, socks_host='', socks_port=0):
        self.host = host
        self.port = int(port)
        self.socks_host = socks_host
        self.socks_port = socks_port
        self.version = version
        self._id = 1
        self.timeout = connect_timeout
        self.connect()

    @property
    def _rpcid(self):
        if self._id >= 1000000:
            self._id = 0
        self._id += 1
        return self._id

    def connect(self):
        plain_socket = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
        plain_socket.settimeout(self.timeout)
        if not self.socks_host== '':
            plain_socket.setproxy(proxy_type=socks.PROXY_TYPE_SOCKS5,addr=self.socks_host,port=self.socks_port,rdns=True)
        plain_socket.connect((self.host, self.port))
        self.socket = ssl.wrap_socket(plain_socket) #, ssl_version=ssl.PROTOCOL_TLSv1, ciphers="ADH-AES256-SHA")


    def close(self):
        self.socket.close()

    def _msg(self, method, params={}, notify=False):
        jsonrpc = {
            'method': method,
            'params': params
        }

        if notify is not True:
            rpcid = copy(self._rpcid)
            jsonrpc['id'] = rpcid

        string = json.dumps(jsonrpc) + '\n'

        if notify:
            return string
        else:
            return (rpcid, string)

    def request(self, method, params={}, retry=1, timeout=2):

        def do_retry(retry):
            retry -= 1
            if retry < 0:
                raise JSONRPCRequestFailure('Retries exceeded.')

            self.close()
            try:
                self.connect()
            except:
                traceback_string = traceback.format_exc()
                logging.error(traceback_string)
            return self.request(method, params, retry-1)

        try:
            rpcid, netstring = self._msg(method, params)

            self.socket.sendall(netstring)
        except:
            # Get the traceback
            tb_s = traceback.format_exc()
            logging.error(tb_s)
            return do_retry(retry)

        response_string = ''
        while not balanced(response_string):
            response_string += str(self.socket.recv(1))

        try:
            response = json.loads(response_string)
        except:
            raise JSONRPCBadResponse(
                'Failed to parse response: {}'.format(response_string))

        if 'id' not in response:
            raise JSONRPCBadResponse("Missing 'id'")

        if response['id'] != rpcid:
            logging.error(
                'Wrong response id. Got {actual}, expects {expected}.'
                ' Retrying...'.format(
                    actual=response['id'],
                    expected=rpcid))
            return do_retry(retry)

        last_char = self.socket.recv(1)

        if 'result' in response:
            return response['result']
        elif 'error' in response:
            error = response['error']
            if 'code' not in error:
                raise JSONRPCBadResponse(
                    'error response missing code. Response: {}'
                    .format(response))
            elif 'message' not in error:
                raise JSONRPCBadResponse(
                    'error response missing message. Response: {}'
                    .format(response))
            raise JSONRPCResponseError(response['error'])
        else:
            raise JSONRPCBadResponse(
                'Invalid response: {}'.format(response))

    def notify(self, method, params={}):
        netstring = self._msg(method, params, notify=True)
        try:
            self.socket.sendall(netstring)
        except Exception:
            self.close()
            try:
                # Retry once
                self.connect()
                self.socket.sendall(netstring)
            except Exception:
                raise JSONRPCRequestFailure('Failed to send.')
