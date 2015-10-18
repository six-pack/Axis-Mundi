import threading
from utilities import queue_task
#import requests
import urllib2
import json
from time import sleep
import socks
from sockshandler import SocksiPyHandler

class btc_exchange_rate(threading.Thread):
    # Thread to handle periodic exchange rate lookups. Queries multiple sources in case of failure
    # Requires a SOCKS proxy to be provided - by default the Tor SOCKS proxy is used

    def __init__(self, socks_proxy, socks_port, queue):
        self.socks_proxy = socks_proxy
        self.socks_port = socks_port
        self.queue = queue
        self.running = True
        threading.Thread.__init__(self)

    def run(self):
        print "BTC Exchange rate thread started using SOCKS proxy " + self.socks_proxy + ":" + self.socks_port
        # Make the request look like it came from a browser TODO - define the browser headers elsewhere so they can be easily updated
        headers = [('User-Agent','Mozilla/5.0 (Windows NT 6.1; rv:31.0) Gecko/20100101 Firefox/31.0'),
                   ('Accept','text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
                   ('Accept-Language','en-us,en;q=0.5')]
        opener = urllib2.build_opener(SocksiPyHandler(socks.SOCKS5, self.socks_proxy, int(self.socks_port)))
        opener.addheaders = headers
        while self.running:
            try:
                response = opener.open('http://bitpay.com/api/rates',None,30).read()
                print "Response" + str(response)
            except:
                print "Warning: Failed to retrieve current exchange rates via https/socks"
                sleep (60) # try again in a minute TODO try other exchange api sources
            else:
                data = json.loads(response)
                task = queue_task(1, 'update_exchange_rates', data)
                print "Exchange rates updated"
                self.queue.put(task)
                sleep(900) # default 15 minutes TODO: Randomize this slightly (between 10 - 30 minutes)

        print "Exchange rate collector shutting down"