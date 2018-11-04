import socket
import threading, sys
import datetime, time, json
from enum import Enum

class PacketType(Enum):
    HEARTBEAT_REQ = 0
    HEARTBEAT_RES = 1
    CONNECT_REQ = 2
    CONNECT_RES = 3
    RTT_REQ = 4
    RTT_RES = 5
    SUM = 6
    MESSAGE_TEXT = 7
    MESSAGE_FILE = 8
    ACK = 9


def create_packet(packet_type, message=None):
    packet = dict()
    packet['packetType'] = packet_type
    if not message is None:
        checksum = 0
        for byte in message:
            checksum += int(byte)
        packet['message'] = message
        packet['checksum'] = checksum
        packet['messageLength'] = len(message)
    else:
        packet['checksum'] = 0
        packet['messageLength'] = 0

    packet_data = json.dumps(packet)
    return packet_data



if not len(sys.argv) == 6:
    exit()

name = sys.argv[1]
local_port = sys.argv[2]
pocAddress = sys.argv[3]
pocPort = sys.argv[4]
maxConnections = sys.argv[5]
connections = dict() # Key: Server Name, Value: (IP, Port)
rTTTimes = dict() # Key: (IP, Port) value: RTT
connectedSums = dict() # Key: (IP, Port) Value: Sum

hubNode = None
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
my_address = (client_socket.getsockname(), local_port)




class ReceivingThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, rTTTimes, connectedSums, hubNode

        data, recieved_address = client_socket.recvfrom(64000)

        #parsing of all recieved messages occurs here

        packet = json.loads(data)
        packet_type = packet['packetType']

        if packet_type == PacketType.SUM:
            message = packet['message']
            sent_sum = int(message.decode("utf-8"))
            connectedSums[recieved_address] = sent_sum

            if len(connectedSums) == len(connections) + 1 and len(connections) > 0:
                if hubNode is None:
                    minAddress = connectedSums.keys()[0]
                    minSum = connectedSums[minAddress]
                    for connectedSum in connectedSums:
                        if connectedSums[connectedSum] < minSum:
                            minSum = connectedSums[connectedSum]
                            minAddress = connectedSum

                    hubNode = minAddress
                elif connectedSums[hubNode] > sent_sum:
                    hubNode = recieved_address

        elif packet_type == PacketType.RTT_RES:
            start_time = rTTTimes[recieved_address]
            end_time = datetime.datetime.now().time()
            rtt = (end_time - start_time).total_seconds() * 1000
            rTTTimes[recieved_address] = rtt

        elif packet_type == PacketType.RTT_REQ:
            rttResponseThread = RTTResponseThread(0, 'RTTResponseThread', recieved_address)
            rttResponseThread.start()

        elif packet_type == PacketType.MESSAGE_TEXT:
            if hubNode == my_address:
                addresses = []
                for connection in connections:
                    addresses.append(connections[connection])

                sendMessage = SendMessageThread(0, 'SendMessageThread', packet['message'], addresses)
                sendMessage.start()



class SendMessageThread(threading.Thread):
    def __init__(self, threadID, name, message, addresses):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.addresses = addresses
        self.message = message

    def run(self):
        packet = create_packet(PacketType.MESSAGE_TEXT, self.message)
        for address in self.addresses:
            client_socket.sendto(packet, address)

class SendFileThread(threading.Thread):
    def __init__(self, threadID, name, file, addresses):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.addresses = addresses
        self.file = file

    def run(self):
        packet = create_packet(PacketType.MESSAGE_FILE, self.file)
        for address in self.addresses:
            client_socket.sendto(packet, address)

class RTTResponseThread(threading.Thread):
    def __init__(self, threadID, name, address):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address

    def run(self):
        packet = create_packet(PacketType.RTT_RES)
        client_socket.sendto(packet, self.address)


class SumThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, rTTTimes, connectedSums, hubNode

        summedValue = 0
        for rtt in rTTTimes:
            value = rTTTimes[rtt]
            summedValue += value

        connectedSums[my_address] = summedValue

        if summedValue < connectedSums[hubNode]:
            hubNode = my_address
        #send summed value to all the connected nodes
        for connection in connections:
            addr = connections[connection]
            message = str(summedValue).encode('utf-8')
            packet = create_packet(PacketType.SUM, message)
            client_socket.sendto(packet, addr)

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
                packet = create_packet(PacketType.RTT_REQ)
                client_socket.sendto(packet, addr)
            time.sleep(0.5)
            recieved_all_responses = True
            for rTTTime in rTTTimes:
                if type(rTTTimes[rTTTime]) == type(datetime.datetime.now()):
                    recieved_all_responses = False
                    break

            if recieved_all_responses:
                sendSumThread = SumThread(10, 'SendSumThread')
                sendSumThread.start()
            time.sleep(4.5)


message = input("Star-Node Command: ")

while not message == 'disconnect':

    if message == 'show-status':
        print("Status ================")
        for x in connections:
            print(x + " : " + connections[x] + " : " + rTTTimes[connections[x]])

        print("Hub Node: ")
        for x in connections:
            if connections[x] == hubNode:
                print(x)
                break
    elif 'send' in message:
        # sending data logic

        info = message.split(" ")[1]
        if hubNode is None:
            addresses = rTTTimes.keys()
        else:
            addresses = [hubNode]
        if "\"" in info:
            parsed_message = str(info[1:-1]).encode('utf-8')

            messageThread = SendMessageThread(0, 'Send Message', parsed_message, addresses)
            messageThread.start()
        else:
            file = open(info, "rb")
            file_data = file.read()
            file.close()

            fileSendThread = SendFileThread(0, 'Send File', file_data, addresses)

    elif 'show-log':
        print("Log")


    message = input("Star-Node Command: ")

