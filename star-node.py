import socket
import threading
import time, json
import sys, copy
from datetime import datetime, date
import pickle

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
    DISCONNECT = 10


def create_packet(packet_type, message=None, sequenceNumber=None):
    packet = dict()
    packet['packetType'] = packet_type
    if not sequenceNumber is None:
        packet['sequence'] = sequenceNumber
    if not message is None:
        packet['message'] = message
        packet['messageLength'] = len(message)
    else:
        packet['messageLength'] = 0

    packet_data = json.dumps(packet)
    return packet_data.encode('utf-8')

#made a seperate function to create file packets
#because json would not serialize them
def create_file_packet(file, sequenceNumber=None):
    packet = dict()
    packet['packetType'] = PacketType.MESSAGE_FILE
    if not sequenceNumber is None:
        packet['sequence'] = sequenceNumber
    packet['message'] = file
    #packet['messageLength'] = len(message)
    packet_data = pickle.dumps(packet)
    return packet_data

my_name = ''
my_port = -1
pocAddress = ''
pocPort = 0
maxConnections = 0
connections = dict() # Key: Server Name, Value: (IP, Port)
#connectionLock = threading.Lock()
rTTTimes = dict() # Key: (IP, Port) value: RTT
#rTTTimesLock = threading.Lock()
startTimes = dict() # Key: (IP, Port) value: startTime for RTT
#startTimesLock = threading.Lock()
connectedSums = dict() # Key: (IP, Port) Value: Sum
#connectedSumsLock = threading.Lock()
receivedAck = dict() # Key: (IP, Port) Value: Bool value for whether or not ack was received
#receivedAckLock = threading.Lock()
heartBeatTimes = dict() # Key: (IP, Port) Value: last time a heartbeat response was received
#heartBeatTimesLock = threading.Lock()

sendingSequenceNumber = dict() #Key : (IP, Port) Value: Sequence number that is being sent
#sendingSequenceNumberLock = threading.Lock()
recievedSequenceNumber = dict() #Key: (IP, Port) Value: Sequence number that was last received
#recievedSequenceNumberLock = threading.Lock()

hubNode = None
client_socket = None
logs = list()
my_address = (0,0)


def disconnect_address(address):
    global hubNode, connectedSums, connections, rTTTimes, startTimes, receivedAck, heartBeatTimes, logs
    print("Hi")
    #connectionLock.acquire()

    for x in connections:
        if connections[x] == address:
            del connections[x]
            break
    # connectionLock.release()
    print(connections)
    if (address in rTTTimes):
        #rTTTimesLock.acquire()
        del rTTTimes[address]
        #rTTTimesLock.release()

    if (address in startTimes):
        #startTimesLock.acquire()
        del startTimes[address]
        #startTimesLock.release()

    if (address in connectedSums):
        #connectedSumsLock.acquire()
        del connectedSums[address]
        #connectedSumsLock.release()

    if (address in receivedAck):
        #receivedAckLock.acquire()
        del receivedAck[address]
        #receivedAckLock.release()

    if (address in heartBeatTimes):
        #heartBeatTimesLock.acquire()
        del heartBeatTimes[address]
        #heartBeatTimesLock.release()

    if (address in sendingSequenceNumber):
        #sendingSequenceNumberLock.acquire()
        del sendingSequenceNumber[address]
        #sendingSequenceNumberLock.release()

    if (address in recievedSequenceNumber):
        #recievedSequenceNumberLock.acquire()
        del recievedSequenceNumber[address]
        #recievedSequenceNumberLock.release()


    if (len(connections) < 2):
        hubNode = None

    if hubNode == address:
        # recalculate hub node
        minAddress = None
        minSum = sys.maxsize
        #connectedSumsLock.acquire()
        for connectedSum in connectedSums:
            if connectedSums[connectedSum] < minSum:
                minSum = connectedSums[connectedSum]
                minAddress = connectedSum
        #connectedSumsLock.release()

        hubNode = minAddress
        logs.append(str(datetime.now().time()) + ' Hub Node Updated: ' + str(hubNode))


class ReceivingThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global hubNode, connectedSums, connections, rTTTimes, startTimes, receivedAck, heartBeatTimes, logs, sendingSequenceNumber, recievedSequenceNumber
        rttReceived = 0

        while True:
            data, recieved_address = client_socket.recvfrom(64000)

            #parsing of all recieved messages occurs here
            try:
                packet = json.loads(data.decode('utf-8'))
            except Exception as e:
                print(data)
                packet = pickle.loads(data)

            packet_type = packet['packetType']

            if packet_type == PacketType.SUM:
                message = packet['message']
                sent_sum = float(message)
                #connectedSumsLock.acquire()
                connectedSums[recieved_address] = sent_sum
                #connectedSumsLock.release()
                logs.append(str(datetime.now().time()) + ' SUM Value Recieved: ' + str(sent_sum) + ' ' + str(recieved_address))

                if len(connectedSums) == len(connections) + 1 and len(connections) > 1:
                    if hubNode is None:
                        minAddress = None
                        minSum = sys.maxsize
                        #connectedSumsLock.acquire()
                        for connectedSum in connectedSums:
                            if connectedSums[connectedSum] < minSum:
                                minSum = connectedSums[connectedSum]
                                minAddress = connectedSum
                        #connectedSumsLock.release()
                        hubNode = minAddress
                        logs.append(str(datetime.now().time()) + ' Hub Node Updated: ' + str(hubNode))

                    else:
                        minAddress = None
                        minSum = sys.maxsize
                        #connectedSumsLock.acquire()
                        for connectedSum in connectedSums:
                            if connectedSums[connectedSum] < minSum:
                                minSum = connectedSums[connectedSum]
                                minAddress = connectedSum
                        #connectedSumsLock.release()
                        if not (minAddress == hubNode):

                            if connectedSums[hubNode] * .9 > minSum:

                                hubNode = minAddress
                                logs.append(str(datetime.now().time()) + ' Hub Node Updated: ' + str(hubNode))


            elif packet_type == PacketType.RTT_RES:
                logs.append(
                    str(datetime.now().time()) + ' RTT Response Recieved: ' + str(recieved_address))

                start_time = startTimes[recieved_address]
                end_time = datetime.now().time()
                rtt = (datetime.combine(date.today(), end_time) - datetime.combine(date.today(), start_time)).total_seconds() * 1000
                #rTTTimesLock.acquire()
                rTTTimes[recieved_address] = rtt
                #rTTTimesLock.release()
                rttReceived += 1

                if (len(connections) == len(rTTTimes) and rttReceived == len(connections)):
                    sendSumThread = SumThread(10, 'SendSumThread')
                    sendSumThread.setDaemon(True)
                    sendSumThread.start()
                    rttReceived = 0

            elif packet_type == PacketType.RTT_REQ:
                logs.append(str(datetime.now().time()) + ' RTT Request Recieved: ' + str(recieved_address))

                rttResponseThread = RTTResponseThread(0, 'RTTResponseThread', recieved_address)
                rttResponseThread.start()

            elif packet_type == PacketType.MESSAGE_TEXT:
                logs.append(str(datetime.now().time()) + ' Message Recieved: ' + str(recieved_address) + ' : ' + str(packet['message']))
                sendACKThread = SendACKThread(0, 'Send ACK Thread', recieved_address, packet['sequence'])
                sendACKThread.start()
                if not recieved_address in recievedSequenceNumber or not recievedSequenceNumber[recieved_address] == packet['sequence']:
                    # recievedSequenceNumberLock.acquire()
                    recievedSequenceNumber[recieved_address] = packet['sequence']
                    # recievedSequenceNumberLock.release()
                    print("new message received from " + str(recieved_address) + ": "+ str(packet['message']))
                    if hubNode == my_address:
                        addresses = []
                        # connectionLock.acquire()
                        for connection in connections:
                            if not connections[connection] == recieved_address:
                                addresses.append(connections[connection])
                        # connectionLock.release()
                        logs.append(str(datetime.now().time()) + ' Message Forwarded: ' + str(addresses))
                        sendMessage = SendMessageThread(0, 'SendMessageThread', packet['message'], addresses)
                        sendMessage.setDaemon(True)
                        sendMessage.start()
                else:
                    logs.append(
                        str(datetime.now().time()) + ' DUPLICATE PACKET: ' + str(recieved_address) + ' : ' + str(
                            packet['message']))
            elif packet_type == PacketType.MESSAGE_FILE:
                logs.append(str(datetime.now().time()) + ' File Recieved: ' + str(recieved_address))
                sendACKThread = SendACKThread(0, 'Send ACK Thread', recieved_address, packet['sequence'])
                sendACKThread.start()
                if not recieved_address in recievedSequenceNumber or not recievedSequenceNumber[recieved_address] == packet['sequence']:
                    # recievedSequenceNumberLock.acquire()
                    recievedSequenceNumber[recieved_address] = packet['sequence']
                    # recievedSequenceNumberLock.release()
                    print("new file received from " + str(recieved_address))#don't want to print the whole file #+ ": "+ str(packet['message']))

                    file_bytes = bytes(packet['message'])
                    new_file = open(str(datetime.now().time()), 'w+b')
                    new_file.write(file_bytes)
                    new_file.close()

                    if hubNode == my_address:
                        addresses = []
                        # connectionLock.acquire()
                        for connection in connections:
                            if not connections[connection] == recieved_address:
                                addresses.append(connections[connection])
                        # connectionLock.release()
                        logs.append(str(datetime.now().time()) + ' Message Forwarded: ' + str(addresses))

                        sendFile = SendFileThread(0, 'SendFileThread', packet['message'], addresses)
                        sendFile.setDaemon(True)
                        sendFile.start()
                else:
                    logs.append(
                        str(datetime.now().time()) + ' DUPLICATE PACKET: ' + str(recieved_address) + ' : ' + str(
                            packet['message']))
            elif packet_type == PacketType.CONNECT_REQ:

                name = packet['message']

                sent_connections = copy.deepcopy(connections)
                sent_connections[my_name] = None

                connectionResponseThread = ConnectionResponseThread(0, 'Connection Response', recieved_address, sent_connections)
                connectionResponseThread.setDaemon(True)
                connectionResponseThread.start()
                # connectionLock.acquire()
                connections[name] = recieved_address
                # connectionLock.release()
                # sendingSequenceNumberLock.acquire()
                sendingSequenceNumber[recieved_address] = 0
                # sendingSequenceNumberLock.release()
                #heartBeatTimesLock.acquire()
                heartBeatTimes[recieved_address] = datetime.now().time()
                #heartBeatTimesLock.release()
                logs.append(
                    str(datetime.now().time()) + 'Connected to New Star Node: ' + str(name) + ' ' + str(
                        recieved_address))
            elif packet_type == PacketType.ACK:
                logs.append(str(datetime.now().time()) + ' ACK Received: ' + str(recieved_address))

                sequence_number = packet['sequence']
                if sequence_number == sendingSequenceNumber[recieved_address]:
                    #receivedAckLock.acquire()
                    receivedAck[recieved_address] = True
                    #receivedAckLock.release()
            elif packet_type == PacketType.HEARTBEAT_REQ:
                logs.append(str(datetime.now().time()) + ' Heartbeat Request Received: ' + str(recieved_address))

                heartBeatResponse = SendHeartbeatResponse(0, 'Send Heartbeat Response', recieved_address)
                heartBeatResponse.start()

            elif packet_type == PacketType.HEARTBEAT_RES:
                logs.append(str(datetime.now().time()) + ' Heartbeat Response Received: ' + str(recieved_address))
                #heartBeatTimesLock.acquire()
                heartBeatTimes[recieved_address] = datetime.now().time()
                #heartBeatTimesLock.release()

            elif packet_type == PacketType.DISCONNECT:
                logs.append(str(datetime.now().time()) + ' DISCONNECT Packet Received: ' + str(recieved_address))
                disconnect_address(recieved_address)
                #disconnect the node

class HeartbeatThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, heartBeatTimes, logs
        while True:
            # connectionLock.acquire()
            for connection in connections:
                address = connections[connection]
                start_time = heartBeatTimes[address]
                end_time = datetime.now().time()
                heartBeatDiff = (datetime.combine(date.today(), end_time) - datetime.combine(date.today(),
                                                                 start_time)).total_seconds()

                if heartBeatDiff > 15:
                    # disconnect the connection
                    logs.append(str(datetime.now().time()) + ' Node Dead: ' + str(address))

                    print('Node disconnected')
                    disconnect_address(address)

            packet = create_packet(PacketType.HEARTBEAT_REQ)
            for connection in connections.values():
                logs.append(str(datetime.now().time()) + ' Heartbeat Request Sent: ' + str(connection))

                client_socket.sendto(packet, connection)

            # connectionLock.release()
            time.sleep(3)

class SendHeartbeatResponse(threading.Thread):
    def __init__(self, threadID, name, address):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address

    def run(self):
        logs.append(str(datetime.now().time()) + ' Heartbeat Response Sent: ' + str(self.address))

        packet = create_packet(PacketType.HEARTBEAT_RES)
        client_socket.sendto(packet, self.address)

class SendACKThread(threading.Thread):
    def __init__(self, threadID, name, address, sequenceNumber):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address
        self.sequenceNumber = sequenceNumber

    def run(self):
        global logs
        packet = create_packet(PacketType.ACK, sequenceNumber=self.sequenceNumber)
        client_socket.sendto(packet, self.address)
        logs.append(str(datetime.now().time()) + ' Sent ACK: ' + str(self.address))

class WaitForACK(threading.Thread):
    def __init__(self, threadID, name, address, waitTime, resendPacket):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address
        self.waitTime = waitTime
        self.resendPacket = resendPacket

    def run(self):
        time.sleep(self.waitTime)
        if not self.address in receivedAck or not receivedAck[self.address]:
            logs.append(str(datetime.now().time()) + ' Resend Packet: ' + str(self.address))
            client_socket.sendto(self.resendPacket, self.address)
            #receivedAckLock.acquire()
            receivedAck[self.address] = False
            #receivedAckLock.release()
            waitForAckThread = WaitForACK(0, 'Wait For Ack', self.address, self.waitTime, self.resendPacket)
            waitForAckThread.start()


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
        global logs, receivedAck, sendingSequenceNumber
        for address in self.addresses:
            #receivedAckLock.acquire()
            receivedAck[address] = False
            #receivedAckLock.release()
            if not address in sendingSequenceNumber:
                sendingSequenceNumber[address] = 0
            else:
                sendingSequenceNumber[address] = (sendingSequenceNumber[address] + 1) % 2

            packet = create_packet(PacketType.MESSAGE_TEXT, self.message, sequenceNumber=sendingSequenceNumber[address])
            client_socket.sendto(packet, address)
            waitForAckThread = WaitForACK(0, 'Wait For Ack', address, (rTTTimes[address]), packet)
            waitForAckThread.start()
            logs.append(str(datetime.now().time()) + ' Message Sent: ' + str(address))


class SendFileThread(threading.Thread):
    def __init__(self, threadID, name, file, addresses):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.addresses = addresses
        self.file = file

    def run(self):
        global logs, receivedAck, sendingSequenceNumber
        for address in self.addresses:
            #receivedAckLock.acquire()
            receivedAck[address] = False
            #receivedAckLock.release()
            # sendingSequenceNumberLock.acquire()
            if not address in sendingSequenceNumber:
                sendingSequenceNumber[address] = 0
            else:
                sendingSequenceNumber[address] = (sendingSequenceNumber[address] + 1) % 2
            # sendingSequenceNumberLock.release()
            packet = create_file_packet(self.file, sequenceNumber=sendingSequenceNumber[address])
            client_socket.sendto(packet, address)
            waitForAckThread = WaitForACK(0, 'Wait For Ack', address, (rTTTimes[address]), packet)
            waitForAckThread.start()
            logs.append(str(datetime.now().time()) + ' File Sent: ' + str(address))


class RTTResponseThread(threading.Thread):
    def __init__(self, threadID, name, address):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address

    def run(self):
        global logs
        packet = create_packet(PacketType.RTT_RES)
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
        #rTTTimesLock.acquire()
        for rtt in rTTTimes:
            value = rTTTimes[rtt]
            summedValue += value
        #rTTTimesLock.release()
        logs.append(str(datetime.now().time()) + ' SUM Calculated: ' + str(summedValue))


        if not (summedValue == 0):
            #connectedSumsLock.acquire()
            connectedSums[my_address] = summedValue
            #connectedSumsLock.release()
            # connectionLock.acquire()
            for connection in connections:
                addr = connections[connection]
                message = str(summedValue)
                packet = create_packet(PacketType.SUM, message)
                client_socket.sendto(packet, addr)
            # connectionLock.release()
        # if hubNode is not None and summedValue < connectedSums[hubNode]:
        #     hubNode = my_address
        #     logs.append(str(datetime.now().time()) + ' Hub Node Updated: ' + str(hubNode))

        #send summed value to all the connected nodes


class RTTThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, startTimes, logs
        while True:
            # connectionLock.acquire()
            for connection in connections:
                addr = connections[connection]
                #startTimesLock.acquire()
                startTimes[addr] = datetime.now().time()
                #startTimesLock.release()
                packet = create_packet(PacketType.RTT_REQ)
                client_socket.sendto(packet, addr)
                logs.append(str(datetime.now().time()) + ' RTT Request Sent: ' + str(addr))
            # connectionLock.release()
            time.sleep(5)

def connect_to_poc(PoC_address, PoC_port):
    global connections, logs
    #this function contacts the poc and receives all of the information
    #about the other active nodes

    #send a CONNECT_REQ packet to PoC
    #i get an error when actually using the PacketType enum so I am using
    #just a string to represent the packet type
    response = None
    received_address = None
    client_socket.settimeout(5)
    received = False
    connect_req_packet = create_packet(PacketType.CONNECT_REQ, message=my_name)
    connection_attempts = 0
    while not received and connection_attempts <= 12:
        client_socket.sendto(connect_req_packet, (PoC_address, PoC_port))
        try:
            response, received_address = client_socket.recvfrom(65507)
            received = True
        except socket.timeout:
            received = False
            connection_attempts += 1
    if connection_attempts > 12:
        return -1
    packet = json.loads(response.decode('utf-8'))
    type = packet["packetType"]
    if type == PacketType.CONNECT_RES:
        new_connections = packet["message"]
        # connectionLock.acquire()
        for new_connection in new_connections:
            logs.append(str(datetime.now().time()) + 'Connected to New Star Node: ' + str(new_connection) + ' ' + str(new_connections[new_connection]))
            if new_connections[new_connection] is None:
                connections[new_connection] = received_address
            else:
                connections[new_connection] = tuple(new_connections[new_connection])
        #heartBeatTimesLock.acquire()
        for connection in connections.values():
            heartBeatTimes[connection] = datetime.now().time()
        #heartBeatTimesLock.release()
        # connectionLock.release()
    client_socket.settimeout(None)
    return 1
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
    # connectionLock.acquire()
    for connection in connections:
        connect_req_packet = create_packet(PacketType.CONNECT_REQ, message=my_name)
        addr = connections[connection]
        client_socket.sendto(connect_req_packet, addr)
        #dont really need to do anything with the response just make sure that
        #there actually was one
    # connectionLock.release()
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
    my_ip = socket.gethostbyname(socket.getfqdn()) #127.0.0.1'
    my_address = (my_ip, my_port)
    client_socket.bind(('', my_port))

    #first we try to connect to the POC
    if (poc_address == '0'):
        #-----------TODO------------------------
        #then this node does not have a PoC so we should just keep running
        #until another node connects to us
        #---------------------------------------
        print("TODO")
    else:
        c = connect_to_poc(poc_address, poc_port)
        if c == -1:
            print("failed to connect to PoC after 1 minute.")
            print("check that PoC is online.")
            sys.exit()
        #if that succeeds then we should have all of the active connections
        #in the network given to us by the poc so lets connect to all of them
        connect_to_network()

        #now everyone is aware that this node is alive so we have completed
        #peer discovery phase. We can now start calculating RTT and find the
        #hub node

    recivingThread = ReceivingThread(0, "Recieving Thread")
    recivingThread.setDaemon(True)
    recivingThread.start()

    #----------------------------------
    #TODO: do RTT stuff and find hub
    #----------------------------------
    rttThread = RTTThread(11, "rttThread")
    rttThread.setDaemon(True)
    rttThread.start()


    #---------------------------------------------------------------------
    #TODO:
    #we have now found the hub and formed the network
    #we now have to be able to send/receive messages, do RTT measurements,
    #Heartbeat stuff, and handle commands by the user
    #---------------------------------------------------------------------

    heartBeatThread = HeartbeatThread(12, "HeartBeat Thread")
    heartBeatThread.setDaemon(True)
    heartBeatThread.start()
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

            info = command[5:]
            if hubNode is None or hubNode == my_address:
                addresses = connections.values()
            else:
                addresses = [hubNode]
            if "\"" in info:
                parsed_message = str(info[1:-1])

                messageThread = SendMessageThread(0, 'Send Message', parsed_message, addresses)
                messageThread.setDaemon(True)
                messageThread.start()
            else:
                file = open(info, "rb")
                file_data = file.read()
                file.close()

                fileSendThread = SendFileThread(0, 'Send File', file_data, addresses)
                fileSendThread.setDaemon(True)
                fileSendThread.start()
        elif command == 'show-log':
            for log in logs:
                print(log)

        command = input("Star-Node Command: ")

    print("disconnecting")
    disconnect_packet = create_packet(PacketType.DISCONNECT)
    for connection in connections.values():
        client_socket.sendto(disconnect_packet, connection)
    client_socket.close()
    sys.exit()
    #TODO handle the disconnect command

if __name__ == "__main__":
    main()
