import socket
import threading
import time, json
import sys, copy
from datetime import datetime, date

class PacketType:
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
        # for byte in message:
        #     checksum += (byte)
        packet['message'] = message
        packet['checksum'] = checksum
        packet['messageLength'] = len(message)
    else:
        packet['checksum'] = 0
        packet['messageLength'] = 0

    packet_data = json.dumps(packet)
    return packet_data.encode('utf-8')

my_name = ''
my_port = -1
pocAddress = ''
pocPort = 0
maxConnections = 0
connections = dict() # Key: Server Name, Value: (IP, Port)
rTTTimes = dict() # Key: (IP, Port) value: RTT
startTimes = dict() # Key: (IP, Port) value: startTime for RTT
connectedSums = dict() # Key: (IP, Port) Value: Sum

hubNode = None
client_socket = None
logs = list()
my_address = (0,0)



class ReceivingThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, rTTTimes, connectedSums, hubNode, startTimes, logs

        while True:
            data, recieved_address = client_socket.recvfrom(64000)

            #parsing of all recieved messages occurs here

            packet = json.loads(data.decode('utf-8'))
            packet_type = packet['packetType']

            if packet_type == PacketType.SUM:
                message = packet['message']
                sent_sum = float(message)
                connectedSums[recieved_address] = sent_sum
                logs.append(str(datetime.now().time()) + ' SUM Value Recieved: ' + str(sent_sum) + ' ' + str(recieved_address))

                if len(connectedSums) == len(connections) + 1 and len(connections) > 1:
                    if hubNode is None:
                        minAddress = None
                        minSum = sys.maxsize
                        for connectedSum in connectedSums:
                            if connectedSums[connectedSum] < minSum:
                                minSum = connectedSums[connectedSum]
                                minAddress = connectedSum

                        hubNode = minAddress
                        logs.append(str(datetime.now().time()) + ' Hub Node Updated: ' + str(hubNode))

                    elif connectedSums[hubNode] > sent_sum:
                        hubNode = recieved_address
                        logs.append(str(datetime.now().time()) + ' Hub Node Updated: ' + str(hubNode))


            elif packet_type == PacketType.RTT_RES:
                print("RTT RESPONSE RECIEVED")
                logs.append(
                    str(datetime.now().time()) + ' RTT Response Recieved: ' + str(recieved_address))

                start_time = startTimes[recieved_address]
                end_time = datetime.now().time()
                rtt = (datetime.combine(date.today(), end_time) - datetime.combine(date.today(), start_time)).total_seconds() * 1000
                rTTTimes[recieved_address] = rtt

            elif packet_type == PacketType.RTT_REQ:
                print("RTT REQUEST RECIEVECD")
                logs.append(str(datetime.now().time()) + ' RTT Request Recieved: ' + str(recieved_address))

                rttResponseThread = RTTResponseThread(0, 'RTTResponseThread', recieved_address)
                rttResponseThread.start()

            elif packet_type == PacketType.MESSAGE_TEXT:
                logs.append(str(datetime.now().time()) + ' Message Recieved: ' + str(recieved_address) + ' : ' + str(packet['message']))

                if hubNode == my_address:
                    addresses = []
                    for connection in connections:
                        if not connections[connection] == recieved_address:
                            addresses.append(connections[connection])
                    logs.append(str(datetime.now().time()) + ' Message Forwarded: ' + str(addresses))
                    sendMessage = SendMessageThread(0, 'SendMessageThread', packet['message'], addresses)
                    sendMessage.start()
            elif packet_type == PacketType.MESSAGE_FILE:
                logs.append(str(datetime.now().time()) + ' Message Recieved: ' + str(recieved_address))
                if hubNode == my_address:
                    addresses = []
                    for connection in connections:
                        if not connections[connection] == recieved_address:
                            addresses.append(connections[connection])
                    logs.append(str(datetime.now().time()) + ' Message Forwarded: ' + str(addresses))

                    sendFile = SendMessageThread(0, 'SendFileThread', packet['message'], addresses)
                    sendFile.start()

            elif packet_type == PacketType.CONNECT_REQ:

                name = packet['message']

                sent_connections = copy.deepcopy(connections)
                sent_connections[my_name] = None
                print("RECEIVED CONNECT REQUEST ")

                connectionResponseThread = ConnectionResponseThread(0, 'Connection Response', recieved_address, sent_connections)

                connectionResponseThread.start()
                connections[name] = recieved_address
                logs.append(
                    str(datetime.now().time()) + 'Connected to New Star Node: ' + str(name) + ' ' + str(
                        recieved_address))


class ConnectionResponseThread(threading.Thread):
    def __init__(self, threadID, name, address, message):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address
        self.message = message

    def run(self):
        packet = create_packet(PacketType.CONNECT_RES, self.message)
        client_socket.sendto(packet, self.address)
class SendMessageThread(threading.Thread):
    def __init__(self, threadID, name, message, addresses):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.addresses = addresses
        self.message = message

    def run(self):
        global logs
        packet = create_packet(PacketType.MESSAGE_TEXT, self.message)
        for address in self.addresses:
            client_socket.sendto(packet, address)
            logs.append(str(datetime.now().time()) + ' Message Sent: ' + str(address))


class SendFileThread(threading.Thread):
    def __init__(self, threadID, name, file, addresses):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.addresses = addresses
        self.file = file

    def run(self):
        global logs
        packet = create_packet(PacketType.MESSAGE_FILE, self.file)
        for address in self.addresses:
            client_socket.sendto(packet, address)
            logs.append(str(datetime.now().time()) + ' Message Sent: ' + str(address))


class RTTResponseThread(threading.Thread):
    def __init__(self, threadID, name, address):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address

    def run(self):
        global logs
        packet = create_packet(PacketType.RTT_RES)
        print("SENT RTT RESPONSE")
        logs.append(str(datetime.now().time()) + ' RTT Response Sent: ' + str(self.address))

        client_socket.sendto(packet, self.address)


class SumThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, rTTTimes, connectedSums, hubNode, logs

        summedValue = 0
        for rtt in rTTTimes:
            value = rTTTimes[rtt]
            summedValue += value
        logs.append(str(datetime.now().time()) + ' SUM Calculated: ' + str(summedValue))

        connectedSums[my_address] = summedValue

        if hubNode is not None and summedValue < connectedSums[hubNode]:
            hubNode = my_address
            logs.append(str(datetime.now().time()) + ' Hub Node Updated: ' + str(hubNode))

        #send summed value to all the connected nodes
        for connection in connections:
            addr = connections[connection]
            message = str(summedValue)
            packet = create_packet(PacketType.SUM, message)
            client_socket.sendto(packet, addr)

class RTTThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, startTimes, logs
        while True:
            for connection in connections:
                addr = connections[connection]
                startTimes[addr] = datetime.now().time()
                packet = create_packet(PacketType.RTT_REQ)
                client_socket.sendto(packet, addr)
                logs.append(str(datetime.now().time()) + ' RTT Request Sent: ' + str(addr))



            sendSumThread = SumThread(10, 'SendSumThread')
            sendSumThread.start()
            time.sleep(5)

def connect_to_poc(PoC_address, PoC_port):
    global connections, logs
    #this function contacts the poc and receives all of the information
    #about the other active nodes

    #send a CONNECT_REQ packet to PoC
    #i get an error when actually using the PacketType enum so I am using
    #just a string to represent the packet type
    connect_req_packet = create_packet(PacketType.CONNECT_REQ, message=my_name)
    client_socket.sendto(connect_req_packet, (PoC_address, PoC_port))
    response, received_address = client_socket.recvfrom(65507)
    packet = json.loads(response.decode('utf-8'))
    type = packet["packetType"]
    if type == PacketType.CONNECT_RES:
        new_connections = packet["message"]
        print("NewConnections: " + str(new_connections))
        for new_connection in new_connections:
            logs.append(str(datetime.now().time()) + 'Connected to New Star Node: ' + str(new_connection) + ' ' + str(new_connections[new_connection]))
            if new_connections[new_connection] is None:
                connections[new_connection] = received_address
            else:
                connections[new_connection] = tuple(new_connections[new_connection])
    #--------------------
    #TODO: handle response. add all connections to global dict
    #--------------------

def connect_to_network():
    #this function goes through the list of active connections and
    #exchanges contact info with all of them so that the whole network is aware
    #that this node is alive now
    #------------------------------
    #TODO: make sure this is correct
    #------------------------------
    for connection in connections:
        connect_req_packet = create_packet(PacketType.CONNECT_REQ, message=my_name)
        addr = connections[connection]
        client_socket.sendto(connect_req_packet, addr)
        #dont really need to do anything with the response just make sure that
        #there actually was one

def main():
    #remember to uncomment the my_address
    #command line looks like this: star-node <name> <local-port> <PoC-address> <PoC-port> <N>
    global my_name, my_port, maxConnections, client_socket, my_address, connections, hubNode, rTTTimes, logs
    my_name = sys.argv[1]
    my_port = int(sys.argv[2])
    poc_address = sys.argv[3]
    poc_port = int(sys.argv[4])
    maxConnections = int(sys.argv[5])

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    my_address = ('127.0.0.1', my_port)
    client_socket.bind(('', my_port))

    #first we try to connect to the POC
    if (poc_address == '0'):
        #-----------TODO------------------------
        #then this node does not have a PoC so we should just keep running
        #until another node connects to us
        #---------------------------------------
        print("TODO")
    else:
        connect_to_poc(poc_address, poc_port)

        #if that succeeds then we should have all of the active connections
        #in the network given to us by the poc so lets connect to all of them
        connect_to_network()

        #now everyone is aware that this node is alive so we have completed
        #peer discovery phase. We can now start calculating RTT and find the
        #hub node

    recivingThread = ReceivingThread(0, "Recieving Thread")
    recivingThread.start()

    #----------------------------------
    #TODO: do RTT stuff and find hub
    #----------------------------------
    rttThread = RTTThread(11, "rttThread")
    rttThread.start()


    #---------------------------------------------------------------------
    #TODO:
    #we have now found the hub and formed the network
    #we now have to be able to send/receive messages, do RTT measurements,
    #Heartbeat stuff, and handle commands by the user
    #---------------------------------------------------------------------
    command = input("Star-Node Command: ")

    while not command == 'disconnect':

        if command == 'show-status':
            print("Status ================")
            print(connections)
            for x in connections:
                print(x + " : " + str(connections[x]) + " : " + str(rTTTimes[connections[x]]))

            print("Hub Node: " + str(hubNode))
            for x in connections:
                if connections[x] == hubNode:
                    print(x)
                    break
        elif 'send' in command:
            # sending data logic

            info = command.split(" ")[1]
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
                fileSendThread.start()
        elif command == 'show-log':
            for log in logs:
                print(log)

        command = input("Star-Node Command: ")


    #TODO handle the disconnect command

if __name__ == "__main__":
    main()
