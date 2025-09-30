#!/usr/bin/env python3
"""
WebSocket to TCP bridge for HyperTCP protocol
This allows web browsers to communicate with the HyperTCP server
"""

import asyncio
import websockets
import socket
import struct
import json
import threading
import time

# HyperTCP protocol constants
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

class WebSocketBridge:
    def __init__(self, tcp_host='127.0.0.1', tcp_port=8080, ws_port=8081):
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self.ws_port = ws_port
        self.tcp_socket = None
        self.websocket = None
        self.connected = False
        
    def connect_to_tcp_server(self):
        """Connect to the HyperTCP server"""
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.connect((self.tcp_host, self.tcp_port))
            self.connected = True
            print(f"Connected to HyperTCP server at {self.tcp_host}:{self.tcp_port}")
            return True
        except Exception as e:
            print(f"Failed to connect to HyperTCP server: {e}")
            return False
    
    def disconnect_from_tcp_server(self):
        """Disconnect from the HyperTCP server"""
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
            self.tcp_socket = None
            self.connected = False
            print("Disconnected from HyperTCP server")
    
    async def handle_websocket(self, websocket):
        """Handle WebSocket connection from web client"""
        print(f"WebSocket client connected from {websocket.remote_address}")
        self.websocket = websocket
        
        # Connect to TCP server
        if not self.connect_to_tcp_server():
            await websocket.close(code=1011, reason="Failed to connect to HyperTCP server")
            return
        
        # Start TCP listener in a separate thread
        tcp_listener_thread = threading.Thread(target=self.tcp_listener)
        tcp_listener_thread.daemon = True
        tcp_listener_thread.start()
        
        try:
            # Handle messages from WebSocket
            async for message in websocket:
                if isinstance(message, bytes):
                    # Binary message - forward to TCP server
                    await self.forward_to_tcp(message)
                else:
                    # Text message - ignore or handle as control message
                    print(f"Received text message: {message}")
        except websockets.exceptions.ConnectionClosed:
            print("WebSocket connection closed")
        except Exception as e:
            print(f"WebSocket error: {e}")
        finally:
            # Clean up
            self.disconnect_from_tcp_server()
            self.websocket = None
    
    async def forward_to_tcp(self, data):
        """Forward data from WebSocket to TCP server"""
        if self.tcp_socket and self.connected:
            try:
                self.tcp_socket.sendall(data)
            except Exception as e:
                print(f"Error forwarding to TCP server: {e}")
                await self.websocket.close(code=1011, reason="TCP connection lost")
    
    def tcp_listener(self):
        """Listen for data from TCP server and forward to WebSocket"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self.connected and self.tcp_socket:
            try:
                # Read header first (5 bytes)
                header_data = self.recv_all(5)
                if not header_data:
                    break
                
                # Forward header to WebSocket
                asyncio.run_coroutine_threadsafe(
                    self.websocket.send(header_data), 
                    loop
                )
                
                # Parse header to get payload length
                header = HyperTCPHeader.unpack(header_data)
                
                # Read payload if any
                if header.length > 0:
                    payload_data = self.recv_all(header.length)
                    if not payload_data:
                        break
                    
                    # Forward payload to WebSocket
                    asyncio.run_coroutine_threadsafe(
                        self.websocket.send(payload_data), 
                        loop
                    )
                    
            except Exception as e:
                print(f"Error in TCP listener: {e}")
                break
        
        # If we get here, the TCP connection was lost
        if self.websocket:
            asyncio.run_coroutine_threadsafe(
                self.websocket.close(code=1011, reason="TCP connection lost"), 
                loop
            )
    
    def recv_all(self, length):
        """Receive exactly 'length' bytes from the TCP socket"""
        data = b''
        while len(data) < length:
            try:
                chunk = self.tcp_socket.recv(length - len(data))
                if not chunk:
                    return None
                data += chunk
            except Exception as e:
                print(f"Error receiving data: {e}")
                return None
        return data
    
    async def start(self):
        """Start the WebSocket server"""
        print(f"Starting WebSocket bridge on port {self.ws_port}")
        print(f"Will forward to HyperTCP server at {self.tcp_host}:{self.tcp_port}")
        
        # Create the server with the correct handler
        server = await websockets.serve(self.handle_websocket, "0.0.0.0", self.ws_port)
        await server.wait_closed()

async def main():
    # Create bridge: WebSocket on port 8081 <-> TCP on port 8080
    bridge = WebSocketBridge(tcp_host='127.0.0.1', tcp_port=8080, ws_port=8081)
    await bridge.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down WebSocket bridge...")