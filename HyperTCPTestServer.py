#!/usr/bin/env python3
"""
Simple server implementation for testing the HyperTCP protocol
Pure TCP implementation without WebSocket or any other protocol
"""

import socket
import struct
import threading
import json
import time
from collections import defaultdict

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

class HyperTCPProtocolServer:
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = {}  # Store individual client connections
        self.device_connections = defaultdict(list)  # Group connections by device ID
        self.admin_clients = set()  # Separate set for admin clients
        self.running = False
        self.device_id = "server"
        self.client_counter = 0
        
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        
        print(f"HyperTCP Server listening on {self.host}:{self.port}")
        
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                print(f"Client connected from {address}")
                
                # Handle client in a separate thread
                client_thread = threading.Thread(
                    target=self.handle_client, 
                    args=(client_socket, address)
                )
                client_thread.daemon = True
                client_thread.start()
                
            except Exception as e:
                if self.running:
                    print(f"Error accepting connections: {e}")
    
    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
            
        # Close all client connections
        for client_id in list(self.clients.keys()):
            try:
                self.clients[client_id]['socket'].close()
            except:
                pass
        self.clients.clear()
        self.device_connections.clear()
        self.admin_clients.clear()
        print("Server stopped and all connections cleaned up")
    
    def handle_client(self, client_socket, address):
        temp_client_id = None
        try:
            authenticated = False
            # Generate a temporary client ID until authentication
            temp_client_id = f"client_{address[0]}_{address[1]}_{self.client_counter}"
            self.client_counter += 1
            
            # Register client with temporary ID
            self.clients[temp_client_id] = {
                'socket': client_socket,
                'address': address,
                'authenticated': False,
                'device_id': None,  # Will be set during authentication
                'connect_time': time.time(),  # Track connection time
                'is_admin': False  # Track if this is an admin client
            }
            
            print(f"Client registered as {temp_client_id}")
            
            while True:
                # Read header (5 bytes)
                header_data = self.recv_all(client_socket, 5)
                if not header_data or len(header_data) < 5:
                    break
                
                header = HyperTCPHeader.unpack(header_data)
                print(f"Received message: type={header.type}, id={header.msg_id}, length={header.length}")
                
                # Read payload if any
                payload = b''
                if header.length > 0:
                    payload = self.recv_all(client_socket, header.length)
                    if not payload:
                        break
                
                # Handle different message types
                if header.type == HYPER_TCP_CMD_LOGIN:
                    # Handle login with device ID
                    try:
                        # Payload should be JSON with token and device_id
                        login_data = json.loads(payload.decode('utf-8'))
                        token = login_data.get("token", "")
                        device_id = login_data.get("device_id", temp_client_id)
                        
                        print(f"Login attempt - Token: {token}, Device ID: {device_id}")
                        
                        # Check if this is an admin client
                        is_admin = device_id.startswith("admin_") or token == "admin_token"
                        
                        # Simple authentication
                        if is_admin:
                            authenticated = (token == "admin_token")
                            status = HYPER_TCP_STATUS_SUCCESS if authenticated else HYPER_TCP_STATUS_INVALID_TOKEN
                        else:
                            authenticated = (token == "your_auth_token_here")
                            status = HYPER_TCP_STATUS_SUCCESS if authenticated else HYPER_TCP_STATUS_INVALID_TOKEN
                        
                        # Update client authentication status
                        self.clients[temp_client_id]['authenticated'] = authenticated
                        self.clients[temp_client_id]['is_admin'] = is_admin
                        
                        # If authenticated, register appropriately
                        if authenticated:
                            # Set the device_id
                            self.clients[temp_client_id]['device_id'] = device_id
                            
                            if is_admin:
                                # Register as admin client
                                self.admin_clients.add(temp_client_id)
                                print(f"Admin client {temp_client_id} authenticated with device ID {device_id}")
                                # Send welcome message
                                self.send_welcome_message(client_socket, temp_client_id)
                                
                                # Send initial connection status for all currently connected devices
                                self.send_initial_connection_status(temp_client_id)
                            else:
                                # Register as regular device client
                                # Add this connection to the device's connection list
                                self.device_connections[device_id].append(temp_client_id)
                                
                                print(f"Client {temp_client_id} authenticated with device ID {device_id}")
                                print(f"Device {device_id} now has {len(self.device_connections[device_id])} connections")
                                # Send welcome message
                                self.send_welcome_message(client_socket, temp_client_id)
                                
                                # Notify admin channels about new connection (if any exist)
                                self.notify_admin_channels({
                                    "event": "deviceConnected",
                                    "deviceId": device_id,
                                    "clientId": temp_client_id,
                                    "timestamp": int(time.time() * 1000)
                                })
                        else:
                            print(f"Client {temp_client_id} failed authentication")
                        
                        # Send response
                        response_header = HyperTCPHeader(HYPER_TCP_CMD_RESPONSE, header.msg_id, 1)
                        client_socket.send(response_header.pack())
                        client_socket.send(struct.pack('!B', status))
                        
                        if not authenticated:
                            break
                        
                    except json.JSONDecodeError:
                        # Fallback to old method for backward compatibility
                        token = payload.decode('utf-8')
                        device_id = temp_client_id
                        is_admin = token == "admin_token"
                        
                        print(f"Login attempt with token: {token}")
                        
                        # Simple authentication
                        if is_admin:
                            authenticated = (token == "admin_token")
                            status = HYPER_TCP_STATUS_SUCCESS if authenticated else HYPER_TCP_STATUS_INVALID_TOKEN
                        else:
                            authenticated = (token == "your_auth_token_here")
                            status = HYPER_TCP_STATUS_SUCCESS if authenticated else HYPER_TCP_STATUS_INVALID_TOKEN
                        
                        # Update client authentication status
                        self.clients[temp_client_id]['authenticated'] = authenticated
                        self.clients[temp_client_id]['is_admin'] = is_admin
                        self.clients[temp_client_id]['device_id'] = device_id
                        
                        # Send response
                        response_header = HyperTCPHeader(HYPER_TCP_CMD_RESPONSE, header.msg_id, 1)
                        client_socket.send(response_header.pack())
                        client_socket.send(struct.pack('!B', status))
                        
                        if authenticated:
                            if is_admin:
                                # Register as admin client
                                self.admin_clients.add(temp_client_id)
                                print(f"Admin client {temp_client_id} authenticated")
                                # Send welcome message
                                self.send_welcome_message(client_socket, temp_client_id)
                                
                                # Send initial connection status for all currently connected devices
                                self.send_initial_connection_status(temp_client_id)
                            else:
                                # Register as regular device client
                                # Add this connection to the device's connection list
                                self.device_connections[device_id].append(temp_client_id)
                                
                                print(f"Client {temp_client_id} authenticated")
                                print(f"Device {device_id} now has {len(self.device_connections[device_id])} connections")
                                # Send welcome message
                                self.send_welcome_message(client_socket, temp_client_id)
                                
                                # Notify admin channels about new connection (if any exist)
                                self.notify_admin_channels({
                                    "event": "deviceConnected",
                                    "deviceId": device_id,
                                    "clientId": temp_client_id,
                                    "timestamp": int(time.time() * 1000)
                                })
                        else:
                            print(f"Client {temp_client_id} failed authentication")
                            break
                        
                elif header.type == HYPER_TCP_CMD_PING:
                    # Send pong response
                    response_header = HyperTCPHeader(HYPER_TCP_CMD_RESPONSE, header.msg_id, 0)
                    client_socket.send(response_header.pack())
                    print("Ping-Pong")
                    
                elif header.type == HYPER_TCP_CMD_JSON_MESSAGE:
                    if self.clients[temp_client_id]['authenticated']:
                        json_data = payload.decode('utf-8')
                        print(f"JSON message received: {json_data}")
                        
                        try:
                            # Parse the JSON message
                            message = json.loads(json_data)
                            
                            # Extract target and payload
                            target_id = message.get("targetId")
                            message_payload = message.get("payload", {})
                            
                            print(f"Target: {target_id}")
                            print(f"Payload: {message_payload}")
                            
                            # Add sender info (use device_id if available)
                            sender_id = self.clients[temp_client_id].get('device_id', temp_client_id)
                            message["from"] = sender_id
                            
                            # Route message based on target
                            self.route_message(sender_id, target_id, message)
                            
                            # If it's a ping command, respond
                            if message_payload.get("command") == "ping":
                                self.send_pong_response(client_socket, message_payload)
                            
                            # Send acknowledgment
                            response_header = HyperTCPHeader(HYPER_TCP_CMD_RESPONSE, header.msg_id, 0)
                            client_socket.send(response_header.pack())
                            
                        except json.JSONDecodeError as e:
                            print(f"JSON decode error: {e}")
                    else:
                        break
                        
                elif header.type == HYPER_TCP_CMD_BROADCAST:
                    if self.clients[temp_client_id]['authenticated']:
                        json_data = payload.decode('utf-8')
                        print(f"Broadcast message received: {json_data}")
                        
                        try:
                            # Parse the JSON message
                            message = json.loads(json_data)
                            
                            # Add sender info (use device_id if available)
                            sender_id = self.clients[temp_client_id].get('device_id', temp_client_id)
                            message["from"] = sender_id
                            
                            # Broadcast to all clients
                            self.broadcast_message(message)
                            
                            # Send acknowledgment
                            response_header = HyperTCPHeader(HYPER_TCP_CMD_RESPONSE, header.msg_id, 0)
                            client_socket.send(response_header.pack())
                            
                        except json.JSONDecodeError as e:
                            print(f"JSON decode error: {e}")
                    else:
                        break
                        
                elif header.type == HYPER_TCP_CMD_RESPONSE:
                    # Just acknowledge responses
                    pass
                    
                else:
                    print(f"Unknown command type: {header.type}")
                    # Send error response
                    response_header = HyperTCPHeader(HYPER_TCP_CMD_RESPONSE, header.msg_id, 1)
                    client_socket.send(response_header.pack())
                    client_socket.send(struct.pack('!B', 2))  # Invalid command
                    
        except Exception as e:
            print(f"Error handling client {temp_client_id}: {e}")
        finally:
            # Clean up the client connection
            self.cleanup_client_connection(temp_client_id, client_socket)
    
    def send_initial_connection_status(self, admin_client_id):
        """Send initial connection status to a newly connected admin client"""
        if admin_client_id not in self.clients:
            return
            
        try:
            # Send information about all currently connected devices
            for device_id, connections in self.device_connections.items():
                for client_id in connections:
                    if client_id in self.clients:
                        connect_time = self.clients[client_id].get('connect_time', time.time())
                        uptime = time.time() - connect_time
                        
                        event_data = {
                            "event": "deviceStatus",
                            "deviceId": device_id,
                            "clientId": client_id,
                            "status": "connected",
                            "uptime": uptime,
                            "timestamp": int(time.time() * 1000)
                        }
                        
                        self.send_to_admin_client(admin_client_id, event_data)
        except Exception as e:
            print(f"Error sending initial connection status to admin {admin_client_id}: {e}")
    
    def send_to_admin_client(self, admin_client_id, event_data):
        """Send event data to a specific admin client"""
        if admin_client_id in self.clients and self.clients[admin_client_id]['authenticated']:
            try:
                json_data = json.dumps(event_data)
                payload_bytes = json_data.encode('utf-8')
                
                header = HyperTCPHeader(HYPER_TCP_CMD_JSON_MESSAGE, 0, len(payload_bytes))
                self.clients[admin_client_id]['socket'].send(header.pack())
                self.clients[admin_client_id]['socket'].send(payload_bytes)
                print(f"Sent admin event to {admin_client_id}: {event_data}")
            except Exception as e:
                print(f"Error sending to admin client {admin_client_id}: {e}")
                # If there's an error sending to admin client, clean up that connection
                self.cleanup_client_connection(admin_client_id, self.clients[admin_client_id]['socket'])
    
    def cleanup_client_connection(self, client_id, client_socket):
        """Clean up a client connection and update device groups"""
        if client_id and client_id in self.clients:
            device_id = self.clients[client_id].get('device_id')
            connect_time = self.clients[client_id].get('connect_time', time.time())
            connection_duration = time.time() - connect_time
            is_admin = self.clients[client_id].get('is_admin', False)
            
            # Remove client from registry
            del self.clients[client_id]
            
            if is_admin:
                # Remove from admin clients set
                self.admin_clients.discard(client_id)
                print(f"Admin client {client_id} disconnected after {connection_duration:.2f} seconds")
            else:
                # Remove from device connections group
                if device_id and device_id in self.device_connections:
                    if client_id in self.device_connections[device_id]:
                        self.device_connections[device_id].remove(client_id)
                        print(f"Removed connection {client_id} from device {device_id}")
                        
                        # Check if device group is now empty
                        if not self.device_connections[device_id]:
                            del self.device_connections[device_id]
                            print(f"Device group {device_id} is now empty and has been removed")
                        
                        # Notify admin channels about disconnection
                        self.notify_admin_channels({
                            "event": "deviceDisconnected",
                            "deviceId": device_id,
                            "clientId": client_id,
                            "connectionDuration": connection_duration,
                            "timestamp": int(time.time() * 1000)
                        })
                
                print(f"Client {client_id} disconnected after {connection_duration:.2f} seconds")
        else:
            print("Client disconnected (no client ID assigned)")
            
        # Always close the socket
        if client_socket:
            try:
                client_socket.close()
            except:
                pass
    
    def notify_admin_channels(self, event_data):
        """Notify all admin channels about connection events"""
        # Send events to all admin clients
        admin_clients_copy = self.admin_clients.copy()
        for admin_client_id in admin_clients_copy:
            self.send_to_admin_client(admin_client_id, event_data)
    
    def route_message(self, sender_id, target_id, message):
        """Route message to appropriate target"""
        print(f"Routing message from {sender_id} to {target_id}")
        
        if target_id == "broadcast":
            # Broadcast to all clients
            self.broadcast_message(message)
        elif target_id == "server":
            # Message to server - handle internally
            self.handle_server_message(sender_id, message)
        elif target_id in self.device_connections:
            # Message to specific device - send to all connections for that device
            self.send_to_device(target_id, message)
        else:
            print(f"Target device {target_id} not found")
    
    def broadcast_message(self, message):
        """Broadcast message to all connected clients"""
        print("Broadcasting message to all clients")
        
        # Send to all clients
        clients_copy = list(self.clients.items())
        for client_id, client_info in clients_copy:
            if client_info['authenticated']:  # Only send to authenticated clients
                try:
                    json_data = json.dumps(message)
                    payload_bytes = json_data.encode('utf-8')
                    
                    header = HyperTCPHeader(HYPER_TCP_CMD_JSON_MESSAGE, 0, len(payload_bytes))
                    client_info['socket'].send(header.pack())
                    client_info['socket'].send(payload_bytes)
                except Exception as e:
                    print(f"Error sending to client {client_id}: {e}")
                    # If there's an error sending to client, clean up that connection
                    self.cleanup_client_connection(client_id, client_info['socket'])
    
    def send_to_device(self, device_id, message):
        """Send message to all connections of a specific device"""
        print(f"Sending message to device {device_id}")
        
        if device_id in self.device_connections:
            # Send to all connections for this device
            connections_copy = self.device_connections[device_id][:]  # Create a copy
            for client_id in connections_copy:
                if client_id in self.clients and self.clients[client_id]['authenticated']:
                    try:
                        json_data = json.dumps(message)
                        payload_bytes = json_data.encode('utf-8')
                        
                        header = HyperTCPHeader(HYPER_TCP_CMD_JSON_MESSAGE, 0, len(payload_bytes))
                        self.clients[client_id]['socket'].send(header.pack())
                        self.clients[client_id]['socket'].send(payload_bytes)
                    except Exception as e:
                        print(f"Error sending to client {client_id}: {e}")
                        # If there's an error sending to client, clean up that connection
                        self.cleanup_client_connection(client_id, self.clients[client_id]['socket'])
    
    def handle_server_message(self, sender_id, message):
        """Handle messages sent directly to the server"""
        print(f"Server received message from {sender_id}: {message}")
        # For now, just acknowledge
        # In a real implementation, you might want to process specific commands here
    
    def send_welcome_message(self, client_socket, client_id):
        """Send welcome message to newly connected client"""
        try:
            welcome_data = {
                "type": "welcome",
                "message": "Connected to HyperTCP server",
                "clientId": client_id,
                "timestamp": int(time.time() * 1000)
            }
            
            json_data = json.dumps(welcome_data)
            payload_bytes = json_data.encode('utf-8')
            
            header = HyperTCPHeader(HYPER_TCP_CMD_JSON_MESSAGE, 0, len(payload_bytes))
            client_socket.send(header.pack())
            client_socket.send(payload_bytes)
            print(f"Sent welcome message to {client_id}")
        except Exception as e:
            print(f"Error sending welcome message to {client_id}: {e}")
    
    def send_pong_response(self, client_socket, ping_payload):
        """Send pong response to ping command"""
        try:
            pong_data = {
                "type": "pong",
                "command": "pong",
                "timestamp": int(time.time() * 1000)
            }
            
            # Merge with original ping payload if needed
            pong_data.update(ping_payload)
            
            json_data = json.dumps(pong_data)
            payload_bytes = json_data.encode('utf-8')
            
            header = HyperTCPHeader(HYPER_TCP_CMD_JSON_MESSAGE, 0, len(payload_bytes))
            client_socket.send(header.pack())
            client_socket.send(payload_bytes)
        except Exception as e:
            print(f"Error sending pong response: {e}")
    
    def recv_all(self, sock, length):
        """Receive exactly 'length' bytes from the socket"""
        data = b''
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return data

if __name__ == "__main__":
    server = HyperTCPProtocolServer()
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()
