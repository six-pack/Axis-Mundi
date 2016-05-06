import threading
from utilities import queue_task, get_age, current_time
import json
from time import sleep
import socks
from sockshandler import SocksiPyHandler
import random
from stratum_rpc import JSONRPCProxy
from multiprocessing import Pool
from multiprocessing.dummy import Pool as ThreadPool
from datetime import datetime, timedelta

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

    def get_random_server(self):
        x= random.randrange(0,len(self.stratum_servers)-1,1)
        (serverstring,) =  self.stratum_servers[x]
        (server,port,connectiontype) = str(serverstring).split(':')
        return (server,port,connectiontype)


    def get_stratum_peers(self):
        attempts = 0
        while attempts < 8:
            sleep(1)
            (server,port,connectiontype) = self.get_random_server()
            print "Info: Updating list of stratum peers via " + str(server) + " attempt #" + str(attempts)
            try:
                jsonrpc = JSONRPCProxy(str(server), int(port), socks_host=str(self.socks_proxy), socks_port=int(self.socks_port),connect_timeout=30)
                response = jsonrpc.request('server.peers.subscribe',timeout=15)
                if not isinstance(response,list):
                    attempts+=1
                    continue
                return (response)
            except:
                attempts+=1
                print "Warning: BTC processor could not query peers on stratum server " + str(server)
                continue
        return  # error

    def cb_get_stratum_peers(self,response):
        if response: # If get peers returned data then process it
            peers=[]
            for peer in response:
                #print peer
                for item in peer[2]:
                    if item[0] == 'p':
                        port = item[1:]
                    if item[0] == 's':
                        ssl = True
                        sport = item[1:]
                if sport: # prefer the ssl port if specified
                    port = sport
                if ssl: # only use servers that support ssl
                    peers.append((peer[1]+':' + port + ':s',)) # why the tuple?
                    #print peers[-1]
            response_msg = queue_task(0,'btc_update_stratum_peers',{'peers':peers})
            # Update our list of peers # TODO - this could be checked and merged with a known-good electrum server list
            self.stratum_servers = peers # update the local list of peers
            self.response_queue.put(response_msg) # also update the backend thread with the current peers so that the config database can be updated
            # TODO: implement dead host checking, especially needed for access through Tor
        else:
            print "Warning: BTC processor unable to refresh list of stratum peers, giving up for now"


    def get_balance(self,addr):
        attempts = 0
        while attempts < 8:
            sleep(1)
            (server,port,connectiontype) = self.get_random_server()
            print "Info: Checking BTC balance for " + str(addr) + " via " + str(server)
            try:
                jsonrpc = JSONRPCProxy(str(server), int(port), socks_host=str(self.socks_proxy), socks_port=int(self.socks_port),connect_timeout=30)
                if isinstance(addr,list):
                    response = []
                    for addr_item in addr:
                        response.append((addr_item,jsonrpc.request('blockchain.address.get_balance',[addr_item],timeout=15)))
                    return (response)
                else:
                    response = jsonrpc.request('blockchain.address.get_balance',[addr],timeout=15)
                    if not isinstance(response,dict):
                        #print "Balance is not a dict..."
                        attempts+=1
                        continue
                    return (addr,response)
            except:
                attempts+=1
                print "Warning: BTC processor could not query balance on stratum server " + str(server)
                continue
        return (addr,-1) # error , return -1


    def cb_get_balance(self,response):
        # TODO - refactor this!
        if not isinstance(response,list):
            (address,balance) = response
            if balance == -1:
                print "Warning: BTC processor unable to get balance for address " + str(address) + ", giving up for now"
                response_msg = queue_task(0,'btc_update_balance',{'address':address,'balance_confirmed':-1,'balance_unconfirmed':-1})
            else:
                response_msg = queue_task(0,'btc_update_balance',{'address':address,'balance_confirmed':balance['confirmed'],'balance_unconfirmed':balance['unconfirmed']})
            self.response_queue.put(response_msg)
        else:
            for response_item in response:
                (address,balance) = response_item
                if balance == -1:
                    print "Warning: BTC processor unable to get balance for address " + str(address) + ", giving up for now"
                    response_msg = queue_task(0,'btc_update_balance',{'address':address,'balance_confirmed':-1,'balance_unconfirmed':-1})
                else:
                    response_msg = queue_task(0,'btc_update_balance',{'address':address,'balance_confirmed':balance['confirmed'],'balance_unconfirmed':balance['unconfirmed']})
                self.response_queue.put(response_msg)

    def get_unspent(self,addr):
        attempts = 0
        while attempts < 8:
            sleep(1)
            (server,port,connectiontype) = self.get_random_server()
            print "Info: Checking BTC unspent outputs for " + str(addr) + " via " + str(server)
            try:
                jsonrpc = JSONRPCProxy(str(server), int(port), socks_host=str(self.socks_proxy), socks_port=int(self.socks_port),connect_timeout=30)
                if isinstance(addr,list):
                    response = []
                    for addr_item in addr:
                        response.append((addr_item,jsonrpc.request('blockchain.address.listunspent',[addr_item],timeout=15)))
                    return (response)
                else:
                    response = jsonrpc.request('blockchain.address.get_history',[addr],timeout=15)
                    if not isinstance(response,list):
                        print "History is not a list..."
                        attempts+=1
                        continue
                    return (addr,response)
            except:
                attempts+=1
                print "Warning: BTC processor could not query balance on stratum server " + str(server)
                continue
        return (addr,-1) # error , return -1


    def cb_get_unspent(self,response):
        # TODO - refactor this!
        if not isinstance(response,list):
            (address,unspent) = response
            if unspent == -1:
                print "Warning: BTC processor unable to get unspent outputs for address " + str(address) + ", giving up for now"
                response_msg = queue_task(0,'btc_update_unspent',{'address':address,'unspent_outputs':-1})
            else:
                response_msg = queue_task(0,'btc_update_unspent',{'address':address,'unspent_outputs':unspent})
            self.response_queue.put(response_msg)
        else:
            for response_item in response:
                (address,unspent) = response_item
                if unspent == -1:
                    print "Warning: BTC processor unable to get unspent outputs for address " + str(address) + ", giving up for now"
                    response_msg = queue_task(0,'btc_update_unspent',{'address':address,'unspent_outputs':-1})
                else:
                    response_msg = queue_task(0,'btc_update_unspent',{'address':address,'unspent_outputs':unspent})
                self.response_queue.put(response_msg)


    def run(self):
        print "Info: BTC processor thread started using SOCKS proxy " + self.socks_proxy + ":" + self.socks_port + " attempting to refresh stratum peers"

        self.pool.apply_async(self.get_stratum_peers, (),callback=self.cb_get_stratum_peers)

        while self.running:
            if not self.request_queue.empty():
                # New BTC processing tasks are here
                task = self.request_queue.get()
                if task.command == 'btc_balance_check':
                    address = task.data['address'] # may be single address or list
                    self.pool.apply_async(self.get_balance, (address,),callback=self.cb_get_balance)
                if task.command == 'btc_get_unspent':
                    address = task.data['address'] # may be single address or list
                    self.pool.apply_async(self.get_unspent, (address,),callback=self.cb_get_unspent)
                elif task.command == 'btc_broadcast_txn':
                    txn = task.data['txn']
                    # TODO: Send txn
                elif task.command == 'shutdown':
                    self.running = False
                else:
                    print "Warning: BTC Processor thread received unknown BTC command"
            sleep (0.1) # rest

        print "Info: BTC Processor shutting down"
        self.pool.close()
        self.pool.join()