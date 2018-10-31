import socket
import threading
import datetime, time


maxConnections = 0
connections = dict()
rTTTimes = dict()
connectedSums = dict()

hubNode = None
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


class ReceivingThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, rTTTimes, connectedSums

        data, recieved_address = client_socket.recvfrom(64000)

        #parsing of all recieved messages occurs here


class SumThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, rTTTimes, connectedSums

        summedValue = 0
        for rtt in rTTTimes:
            value = rTTTimes[rtt]
            summedValue += value

        #send summed value to all the connected nodes
        for connection in connections:
            addr = connections[connection]
            client_socket.sendto('MESSAGE HERE', addr)

class RTTThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, rTTTimes
        while True:
            for connection in connections:
                addr = connections[connection]
                rTTTimes[addr] = datetime.datetime.now().time()
                client_socket.sendto('MESSAGE HERE', addr)
            time.sleep(5)


