import threading
from utilities import queue_task
import json
from time import sleep
import socks
from sockshandler import SocksiPyHandler
import random
from stratum_rpc import JSONRPCProxy
from multiprocessing import Pool
from multiprocessing.dummy import Pool as ThreadPool

class btc_processor(threading.Thread):
    # Thread to handle BTC operations. Queries multiple stratum servers in case of failure
    # Requires a SOCKS proxy to be provided - by default the Tor SOCKS proxy is used

    def __init__(self, socks_proxy, socks_port, stratum_servers, req_queue, res_queue):
        self.socks_proxy = socks_proxy
        self.socks_port = socks_port
        self.request_queue = req_queue
        self.response_queue = res_queue
        self.stratum_servers = stratum_servers
        self.running = True
        self.pool = ThreadPool(processes=4) # maximum of 4 BTC operations will be allowed in parallel
        threading.Thread.__init__(self)

    def get_stratum_peers(self,id):
        jsonrpc = JSONRPCProxy('electrum.no-ip.org', 50002, socks_host=str(self.socks_proxy), socks_port=int(self.socks_port)) # TODO use random server from pool
        try:
            response = jsonrpc.request('server.peers.subscribe',timeout=20)
        except:
            return ('error') # could not get peers
        return (response)

    def get_balance(self,addr):
        jsonrpc = JSONRPCProxy('electrum.no-ip.org', 50002, socks_host=str(self.socks_proxy), socks_port=int(self.socks_port)) # TODO use random server from pool
        try:
            response = jsonrpc.request('blockchain.address.get_balance',[addr],timeout=2)
        except:
            #print "Warning: unable to check BTC balance for " + str(addr)
            return (addr,-1)
        return (addr,response)


    def cb_get_balance(self,response):
        (address,balance) = response
        if response == -1:
            response_msg = queue_task(0,'btc_update_balance',{'address':address,'balance_confirmed':-1,'balance_unconfirmed':-1})
        else:
            response_msg = queue_task(0,'btc_update_balance',{'address':address,'balance_confirmed':balance['confirmed'],'balance_unconfirmed':balance['unconfirmed']})
        self.response_queue.put(response_msg)


    def run(self):
        print "BTC processor thread started using SOCKS proxy " + self.socks_proxy + ":" + self.socks_port

        while self.running:
            if not self.request_queue.empty():
                # New BTC processing tasks are here
                task = self.request_queue.get()
                if task.command == 'btc_balance_check':
                    address = task.data['address']
                    self.pool.apply_async(self.get_balance, (address,),callback=self.cb_get_balance)
                elif task.command == 'btc_broadcast_txn':
                    txn = task.data['txn']
                    # TODO: Send txn
                else:
                    print "Warning: BTC Processor thread received unknown BTC operation"
            sleep (30) # try again in 30 seconds


        print "BTC Processor shutting down"