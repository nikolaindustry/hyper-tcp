#!/usr/bin/env python3
"""
Simple TCP client for testing the HyperTCP protocol
This client can be used to test communication with the HyperTCP server
"""

import socket
import struct
import json
import time
import threading

# Protocol definitions (HyperTCP)
HYPER_TCP_CMD_RESPONSE      = 0
HYPER_TCP_CMD_PING          = 6
HYPER_TCP_CMD_LOGIN         = 29
HYPER_TCP_CMD_JSON_MESSAGE  = 30
HYPER_TCP_CMD_REDIRECT      = 41
HYPER_TCP_CMD_BROADCAST     = 50

HYPER_TCP_STATUS_SUCCESS           = 200
HYPER_TCP_STATUS_INVALID_TOKEN     = 9
HYPER_TCP_STATUS_NOT_AUTHENTICATED = 5
HYPER_TCP_STATUS_TIMEOUT           = 16

class HyperTCPHeader:
    def __init__(self, type=0, msg_id=0, length=0):
        self.type = type
        self.msg_id = msg_id
        self.length = length
    
    def pack(self):
        return struct.pack('!BHH', self.type, self.msg_id, self.length)
    
    @classmethod
    def unpack(cls, data):
        type, msg_id, length = struct.unpack('!BHH', data)
        return cls(type, msg_id, length)

class HyperTCPClient:
    def __init__(self, host='localhost', port=8080, device_id=None):
        self.host = host
        self.port = port
        self.device_id = device_id or f"device_{int(time.time() * 1000) % 100000}"
        self.socket = None
        self.connected = False
        self.message_id = 1
        self.running = False

    def connect(self, token="your_auth_token_here"):
        """Connect to the HyperTCP server and authenticate"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            
            # Send login command with device ID
            if self.send_login(token, self.device_id):
                # Wait for messages and handle them appropriately
                login_response_received = False
                welcome_message_received = False
                authenticated = False
                
                # We might receive multiple messages, so we'll loop until we get the login response
                while not login_response_received:
                    response = self.receive_message()
                    if not response:
                        print("No response received from server")
                        return False
                    
                    if response['type'] == HYPER_TCP_CMD_RESPONSE:
                        # This is the login response
                        status = response['payload'][0] if response['payload'] else 0
                        if status == HYPER_TCP_STATUS_SUCCESS:
                            print(f"Authentication successful for device {self.device_id}")
                            authenticated = True
                        else:
                            print(f"Authentication failed with status: {status}")
                            return False
                        login_response_received = True
                        
                    elif response['type'] == HYPER_TCP_CMD_JSON_MESSAGE:
                        # This might be the welcome message
                        try:
                            json_data = response['payload'].decode('utf-8')
                            welcome_data = json.loads(json_data)
                            print(f"Received welcome message: {welcome_data.get('payload', {})}")
                            welcome_message_received = True
                        except Exception as e:
                            print(f"Error parsing message: {e}")
                            
                    else:
                        print(f"Received unexpected message type: {response['type']}")
                
                if authenticated:
                    self.running = True
                    
                    # Start receiving thread
                    receive_thread = threading.Thread(target=self.receive_loop)
                    receive_thread.daemon = True
                    receive_thread.start()
                    
                    return True
                else:
                    return False
            else:
                print("Failed to send login command")
                return False
                
        except Exception as e:
            print(f"Connection error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from the server"""
        self.running = False
        self.connected = False
        if self.socket:
            self.socket.close()
    
    def send_login(self, token, device_id=None):
        """Send login command to server with device ID"""
        try:
            # Create login data with token and device_id
            login_data = {
                "token": token,
                "device_id": device_id or self.device_id
            }
            
            # Serialize to JSON
            json_data = json.dumps(login_data)
            payload_bytes = json_data.encode('utf-8')
            
            header = HyperTCPHeader(HYPER_TCP_CMD_LOGIN, 1, len(payload_bytes))
            
            self.socket.send(header.pack())
            self.socket.send(payload_bytes)
            return True
        except Exception as e:
            print(f"Error sending login: {e}")
            return False
    
    def send_message(self, target_id, payload):
        """Send a JSON message to a specific target"""
        try:
            # Create message
            message = {
                "targetId": target_id,
                "payload": payload
            }
            
            # Serialize to JSON
            json_data = json.dumps(message)
            payload_bytes = json_data.encode('utf-8')
            
            # Send message
            header = HyperTCPHeader(HYPER_TCP_CMD_JSON_MESSAGE, self.message_id, len(payload_bytes))
            self.message_id += 1
            
            self.socket.send(header.pack())
            self.socket.send(payload_bytes)
            return True
        except Exception as e:
            print(f"Error sending message: {e}")
            return False
    
    def broadcast_message(self, payload):
        """Send a broadcast message to all clients"""
        try:
            # Create message
            message = {
                "targetId": "broadcast",
                "payload": payload
            }
            
            # Serialize to JSON
            json_data = json.dumps(message)
            payload_bytes = json_data.encode('utf-8')
            
            # Send broadcast
            header = HyperTCPHeader(HYPER_TCP_CMD_BROADCAST, self.message_id, len(payload_bytes))
            self.message_id += 1
            
            self.socket.send(header.pack())
            self.socket.send(payload_bytes)
            return True
        except Exception as e:
            print(f"Error sending broadcast: {e}")
            return False
    
    def send_ping(self):
        """Send a ping to the server"""
        try:
            header = HyperTCPHeader(HYPER_TCP_CMD_PING, self.message_id, 0)
            self.message_id += 1
            
            self.socket.send(header.pack())
            return True
        except Exception as e:
            print(f"Error sending ping: {e}")
            return False
    
    def receive_message(self):
        """Receive a single message from the server"""
        try:
            # Read header (5 bytes)
            header_data = self.recv_all(5)
            if not header_data or len(header_data) < 5:
                return None
            
            header = HyperTCPHeader.unpack(header_data)
            
            # Read payload if any
            payload = b''
            if header.length > 0:
                payload = self.recv_all(header.length)
                if not payload:
                    return None
            
            return {
                'type': header.type,
                'msg_id': header.msg_id,
                'length': header.length,
                'payload': payload
            }
        except Exception as e:
            print(f"Error receiving message: {e}")
            return None
    
    def receive_loop(self):
        """Continuously receive messages from the server"""
        while self.running and self.connected:
            try:
                message = self.receive_message()
                if message:
                    self.handle_message(message)
                else:
                    # Connection closed
                    self.connected = False
                    self.running = False
                    break
            except Exception as e:
                if self.running:
                    print(f"Error in receive loop: {e}")
                break
    
    def handle_message(self, message):
        """Handle received messages"""
        msg_type = message['type']
        msg_id = message['msg_id']
        payload = message['payload']
        
        if msg_type == HYPER_TCP_CMD_RESPONSE:
            print(f"Received response (ID: {msg_id})")
            if len(payload) == 1:
                status = payload[0]
                print(f"  Status: {status}")
        
        elif msg_type == HYPER_TCP_CMD_JSON_MESSAGE:
            try:
                json_data = payload.decode('utf-8')
                msg = json.loads(json_data)
                print(f"Received JSON message (ID: {msg_id}):")
                print(f"  From: {msg.get('from', 'unknown')}")
                print(f"  Payload: {msg.get('payload', {})}")
            except Exception as e:
                print(f"Error parsing JSON message: {e}")
        
        elif msg_type == HYPER_TCP_CMD_BROADCAST:
            try:
                json_data = payload.decode('utf-8')
                msg = json.loads(json_data)
                print(f"Received broadcast message (ID: {msg_id}):")
                print(f"  From: {msg.get('from', 'unknown')}")
                print(f"  Payload: {msg.get('payload', {})}")
            except Exception as e:
                print(f"Error parsing broadcast message: {e}")
        
        elif msg_type == HYPER_TCP_CMD_PING:
            print(f"Received ping (ID: {msg_id})")
            # Send pong response
            response_header = HyperTCPHeader(HYPER_TCP_CMD_RESPONSE, msg_id, 0)
            self.socket.send(response_header.pack())
        
        else:
            print(f"Received unknown message type: {msg_type} (ID: {msg_id})")
    
    def recv_all(self, length):
        """Receive exactly 'length' bytes from socket"""
        data = b''
        while len(data) < length:
            packet = self.socket.recv(length - len(data))
            if not packet:
                return None
            data += packet
        return data

def main():
    """Main function for testing the HyperTCP client"""
    # Create client with a specific device ID
    client = HyperTCPClient('localhost', 8080, "sensor_device_001")
    
    # Connect to server
    if not client.connect("your_auth_token_here"):
        print("Failed to connect to server")
        return
    
    print(f"Connected to HyperTCP server as {client.device_id}")
    
    try:
        # Send welcome message
        welcome_payload = {
            "command": "welcome",
            "message": f"Hello from {client.device_id}"
        }
        client.send_message("server", welcome_payload)
        
        # Send periodic messages
        counter = 0
        while client.connected:
            # Send sensor data every 5 seconds
            if counter % 5 == 0:
                sensor_payload = {
                    "command": "sensor_data",
                    "temperature": 20 + (counter % 10),
                    "humidity": 50 + (counter % 20),
                    "timestamp": int(time.time() * 1000)
                }
                client.send_message("server", sensor_payload)
                print(f"Sent sensor data: {sensor_payload}")
            
            # Send ping every 10 seconds
            if counter % 10 == 5:
                client.send_ping()
                print("Sent ping")
            
            # Send broadcast every 30 seconds
            if counter % 30 == 15:
                broadcast_payload = {
                    "command": "notification",
                    "message": f"System notification #{counter//30} from {client.device_id}",
                    "timestamp": int(time.time() * 1000)
                }
                client.broadcast_message(broadcast_payload)
                print(f"Sent broadcast: {broadcast_payload}")
            
            counter += 1
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("Shutting down client...")
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()