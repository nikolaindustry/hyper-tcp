# HyperTCP Protocol Implementation

This implementation provides the HyperTCP protocol - a lightweight, real-time TCP-based protocol for hardware-to-server and server-to-web communication. It's designed as a pure alternative to WebSocket and other protocols, running directly on the TCP layer.

## Key Features

1. **Pure TCP Implementation**: No WebSocket, HTTP, or other intermediate protocols
2. **Lightweight**: Minimal overhead for efficient communication
3. **Real-time**: Low-latency communication for time-sensitive applications
4. **Cross-Platform**: Works with hardware devices, servers, and web applications
5. **JSON Message Support**: Flexible JSON payloads for complex data structures
6. **Authentication**: Token-based authentication for security
7. **Keepalive**: Automatic ping/pong mechanism for connection health
8. **Broadcast Messaging**: Send messages to all connected clients
9. **Server Redirection**: Supports server redirection for load balancing
10. **Extensible**: Easy to add new command types

## Protocol Structure

### Binary Header (4 bytes)
```
struct HyperTCPHeader {
    uint8_t  type;      // Command type
    uint16_t msg_id;    // Message ID
    uint16_t length;    // Payload length
};
```

### Supported Commands
- `HYPER_TCP_CMD_RESPONSE` (0): Response to commands
- `HYPER_TCP_CMD_PING` (6): Keepalive message
- `HYPER_TCP_CMD_LOGIN` (29): Authentication
- `HYPER_TCP_CMD_JSON_MESSAGE` (30): JSON messages
- `HYPER_TCP_CMD_REDIRECT` (41): Server redirection
- `HYPER_TCP_CMD_BROADCAST` (50): Broadcast message to all clients

### Status Codes
- `HYPER_TCP_STATUS_SUCCESS` (200): Operation successful
- `HYPER_TCP_STATUS_INVALID_TOKEN` (9): Invalid authentication token
- `HYPER_TCP_STATUS_NOT_AUTHENTICATED` (5): Client not authenticated
- `HYPER_TCP_STATUS_TIMEOUT` (16): Operation timed out

## Message Format

### Outgoing Messages (Device/Client to Receiver)
```json
{
  "targetId": "receiver_id",
  "payload": {
    // Your data here
  }
}
```

### Incoming Messages (Sender to Device/Client)
```json
{
  "from": "sender_id",
  "payload": {
    // Your data here
  }
}
```

## How to Use

### Arduino/ESP32 Side

1. Include the header file:
```cpp
#include "HyperTCPProtocol.h"
```

2. Set up the transport:
```cpp
WiFiClient wifiClient;
HyperTCPTransport<WiFiClient> myTransport(wifiClient);
```

3. Create the protocol instance:
```cpp
HyperTCPProtocol<HyperTCPTransport<WiFiClient>> myProtocol(myTransport);
```

4. Connect with authentication:
```cpp
myProtocol.connect("your_auth_token", "your-server.com", 8080);
```

5. Send messages:
```cpp
// Method 1: Using JsonObject
DynamicJsonDocument doc(256);
doc["temperature"] = 25.6;
myProtocol.sendMessage("server", doc.as<JsonObject>());

// Method 2: Using JSON string
const char* payload = "{\"temperature\": 25.6}";
myProtocol.sendMessage("server", payload);

// Method 3: Broadcast to all clients
DynamicJsonDocument broadcastDoc(256);
broadcastDoc["notification"] = "System update available";
myProtocol.broadcastMessage(broadcastDoc.as<JsonObject>());

// Method 4: Send directly to server
DynamicJsonDocument serverDoc(256);
serverDoc["status"] = "online";
myProtocol.sendToServer(serverDoc.as<JsonObject>());
```

6. Handle incoming messages:
```cpp
class MyProtocolWithHandlers : public HyperTCPProtocol<HyperTCPTransport<WiFiClient>> {
public:
    MyProtocolWithHandlers(HyperTCPTransport<WiFiClient>& transport) 
        : HyperTCPProtocol<HyperTCPTransport<WiFiClient>>(transport) {}

    void onMessageReceived(const char* from, JsonObject& payload) override {
        // Handle incoming messages
        Serial.print("Message from: ");
        Serial.println(from);
        // Process payload...
    }
    
    void onBroadcastMessage(const char* from, JsonObject& payload) override {
        // Handle broadcast messages
        Serial.print("Broadcast from: ");
        Serial.println(from);
        // Process payload...
    }
};
```

7. Run the protocol loop:
```cpp
void loop() {
    myProtocol.run(); // Call this regularly
}
```

## Server Implementation

The Python server implementation ([HyperTCPTestServer.py](file://c%3A/Users/user/Downloads/myownprotocol/HyperTCPTestServer.py)) provides:

1. **Pure TCP Server**: No WebSocket or HTTP dependencies
2. **Multi-client Support**: Handles multiple concurrent connections
3. **Message Routing**: Routes messages between clients
4. **Authentication**: Token-based client authentication
5. **Broadcast Support**: Send messages to all connected clients
6. **Keepalive**: Monitors connection health with ping/pong

### Running the Server
```bash
python HyperTCPTestServer.py
```

## Communication Types Supported

### Device-to-Server
- Hardware devices can send data to the server
- Server can send commands to specific devices

### Server-to-Device
- Server can push commands and updates to devices
- Real-time control of hardware

### Device-to-Device
- Devices can communicate directly through the server
- Server acts as message broker

### Broadcast
- Messages can be sent to all connected clients
- Useful for notifications and system-wide commands

## Example Message Types

### Sensor Data
```json
{
  "targetId": "server",
  "payload": {
    "temperature": 25.6,
    "humidity": 65.3,
    "timestamp": 1234567890
  }
}
```

### Control Command
```json
{
  "targetId": "device_192.168.1.100_8080",
  "payload": {
    "command": "control",
    "device": "relay_1",
    "action": "toggle",
    "value": 1
  }
}
```

### Ping/Pong
```json
// Outgoing ping
{
  "targetId": "server",
  "payload": {
    "command": "ping",
    "timestamp": 1234567890
  }
}

// Incoming pong
{
  "from": "server",
  "payload": {
    "command": "pong",
    "timestamp": 1234567890
  }
}
```

### Broadcast Notification
```json
{
  "targetId": "broadcast",
  "payload": {
    "command": "notification",
    "message": "System maintenance in 5 minutes",
    "urgency": "medium"
  }
}
```

## Testing

### Hardware Testing
1. Upload [HyperTCPExample.ino](file://c%3A/Users/user/Downloads/myownprotocol/HyperTCPExample.ino) to your ESP32
2. Update WiFi credentials and server IP
3. Run the HyperTCP server
4. Monitor serial output to see messages being exchanged

### Server Testing
1. Run: `python HyperTCPTestServer.py`
2. Connect devices or use a TCP client to test
3. Monitor server console for message logs

## Benefits of HyperTCP

1. **Efficiency**: Pure TCP with minimal overhead
2. **Simplicity**: No complex protocol layers
3. **Real-time**: Low-latency communication
4. **Flexibility**: JSON payloads for complex data
5. **Reliability**: Built-in error handling and connection management
6. **Scalability**: Can handle multiple connections efficiently
7. **Security**: Token-based authentication
8. **Compatibility**: Works with existing network infrastructure

## Performance Considerations

1. **Memory Usage**: JSON parsing requires memory - optimize buffer sizes for constrained devices
2. **Bandwidth**: JSON messages are larger than binary equivalents but still efficient
3. **Processing Time**: JSON parsing is slower than binary but acceptable for most applications
4. **Connection Management**: TCP connections are more resource-intensive than UDP but provide reliability

## Security Considerations

For production use, consider:
- Adding encryption (TLS/SSL for the transport)
- Implementing proper authentication with secure tokens
- Adding message integrity checks
- Including timestamps to prevent replay attacks
- Implementing rate limiting to prevent abuse

## Comparison with WebSocket

| Feature | HyperTCP | WebSocket |
|---------|----------|-----------|
| Protocol Layer | Pure TCP | HTTP + WebSocket |
| Overhead | Minimal | Higher (HTTP headers) |
| Complexity | Low | Medium |
| Browser Support | Requires TCP library | Native |
| Real-time Performance | Excellent | Good |
| Authentication | Built-in | Custom implementation |

## Future Enhancements

1. **Encryption Support**: Add TLS/SSL encryption
2. **Message Compression**: Implement payload compression for bandwidth optimization
3. **Priority Queuing**: Add message priority levels
4. **Quality of Service**: Implement QoS levels for critical messages
5. **Clustering**: Support for distributed server clusters
6. **Persistence**: Add message persistence for offline clients