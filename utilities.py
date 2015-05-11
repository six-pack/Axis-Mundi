from datetime import datetime


class queue_task(object):   # Tasks passed from the front end to the main thread for processing
    def __init__ (self, id, command, data):
        self.id = id
        self.command = command
        self.data = data

def current_time():
    utc_datetime = datetime.utcnow()
    return utc_datetime.strftime("%Y-%m-%d %H:%M")+":00" # always zero seconds to reduce impact of clock time skew leakage

