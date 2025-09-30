/**
 * @file       HyperTCPProtocol.h
 * @author     Your Name
 * @license    MIT License
 * @date       2025
 * @brief      HyperTCP - A lightweight, real-time TCP-based protocol for hardware-to-server and server-to-web communication
 */

#ifndef HyperTCPProtocol_h
#define HyperTCPProtocol_h

#include <Arduino.h>
#include <Client.h>
#include <ArduinoJson.h>

// Protocol command definitions (HyperTCP)
enum HyperTCPCmd {
    HYPER_TCP_CMD_RESPONSE      = 0,
    HYPER_TCP_CMD_PING          = 6,
    HYPER_TCP_CMD_LOGIN         = 29,
    HYPER_TCP_CMD_JSON_MESSAGE  = 30,  // JSON messages
    HYPER_TCP_CMD_REDIRECT      = 41,
    HYPER_TCP_CMD_BROADCAST     = 50   // Broadcast message to all clients
};

// Status codes
enum HyperTCPStatus {
    HYPER_TCP_STATUS_SUCCESS              = 200,
    HYPER_TCP_STATUS_INVALID_TOKEN        = 9,
    HYPER_TCP_STATUS_NOT_AUTHENTICATED    = 5,
    HYPER_TCP_STATUS_TIMEOUT              = 16
};

// Message header structure (HyperTCP)
struct HyperTCPHeader {
    uint8_t  type;      // Command type
    uint16_t msg_id;    // Message ID
    uint16_t length;    // Payload length
} __attribute__((packed));

// Macro to handle byte order
#if defined(ESP32) || defined(ESP8266)
    #include <lwip/def.h>
#elif !defined(htons) && (defined(ARDUINO) || defined(PARTICLE) || defined(__MBED__))
    #if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
        #define htons(x) ( ((x)<<8) | (((x)>>8)&0xFF) )
        #define htonl(x) ( ((x)<<24 & 0xFF000000UL) | \
                           ((x)<< 8 & 0x00FF0000UL) | \
                           ((x)>> 8 & 0x0000FF00UL) | \
                           ((x)>>24 & 0x000000FFUL) )
        #define ntohs(x) htons(x)
        #define ntohl(x) htonl(x)
    #elif __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
        #define htons(x) (x)
        #define htonl(x) (x)
        #define ntohs(x) (x)
        #define ntohl(x) (x)
    #else
        #error "Byte order not defined"
    #endif
#endif

// Transport layer class for TCP
template <typename TClient>
class HyperTCPTransport {
public:
    HyperTCPTransport(TClient& client) 
        : _client(&client), _domain(NULL), _port(0), _connected(false) {}
    
    HyperTCPTransport() 
        : _client(NULL), _domain(NULL), _port(0), _connected(false) {}

    void setClient(TClient* client) {
        _client = client;
        _client->setTimeout(5000); // 5 second timeout
    }

    void begin(const char* domain, uint16_t port) {
        _domain = domain;
        _port = port;
    }

    void begin(IPAddress ip, uint16_t port) {
        _ip = ip;
        _port = port;
        _useIP = true;
    }

    bool connect() {
        if (!_client) return false;
        
        if (_useIP) {
            _connected = (_client->connect(_ip, _port) == 1);
        } else {
            _connected = (_client->connect(_domain, _port) == 1);
        }
        
        return _connected;
    }

    void disconnect() {
        if (_client && _connected) {
            _client->stop();
        }
        _connected = false;
    }

    size_t read(void* buffer, size_t len) {
        if (!_client) return 0;
        return _client->readBytes((char*)buffer, len);
    }

    size_t write(const void* buffer, size_t len) {
        if (!_client) return 0;
        return _client->write((const uint8_t*)buffer, len);
    }

    bool connected() {
        if (!_client) return false;
        return _connected && _client->connected();
    }

    int available() {
        if (!_client) return 0;
        return _client->available();
    }

private:
    TClient*    _client;
    const char* _domain;
    IPAddress   _ip;
    uint16_t    _port;
    bool        _connected = false;
    bool        _useIP = false;
};

// Main protocol class with JSON support
template <class Transport>
class HyperTCPProtocol {
public:
    enum ProtocolState {
        STATE_DISCONNECTED,
        STATE_CONNECTING,
        STATE_CONNECTED,
        STATE_AUTHENTICATED
    };

    HyperTCPProtocol(Transport& transport) 
        : _transport(transport), _state(STATE_DISCONNECTED), _msgId(0) {}

    bool connect(const char* token, const char* server = "your-server.com", uint16_t port = 80) {
        _transport.disconnect();
        _state = STATE_CONNECTING;
        _transport.begin(server, port);
        
        unsigned long start = millis();
        while ((millis() - start) < 10000) { // 10 second timeout
            if (_transport.connect()) {
                // Send login command
                if (sendLogin(token)) {
                    // Wait for response
                    if (waitForLoginResponse(5000)) {
                        _state = STATE_AUTHENTICATED;
                        return true;
                    }
                }
                break;
            }
            delay(100);
        }
        
        _state = STATE_DISCONNECTED;
        return false;
    }

    void disconnect() {
        _transport.disconnect();
        _state = STATE_DISCONNECTED;
    }

    bool run() {
        if (_state == STATE_DISCONNECTED) {
            return false;
        }

        // Process incoming messages
        while (_transport.available() > 0) {
            if (!processInput()) {
                disconnect();
                return false;
            }
        }

        // Send periodic ping
        static unsigned long lastPing = 0;
        if (_state == STATE_AUTHENTICATED && (millis() - lastPing > 30000)) { // 30 seconds
            sendCmd(HYPER_TCP_CMD_PING, 0, NULL, 0);
            lastPing = millis();
        }

        return true;
    }

    // Send JSON message to specific target
    bool sendMessage(const char* targetId, JsonObject& payload) {
        if (_state != STATE_AUTHENTICATED) return false;
        
        // Create JSON document
        DynamicJsonDocument doc(512);
        doc["targetId"] = targetId;
        doc["payload"] = payload;
        
        // Serialize to JSON string
        char buffer[512];
        size_t len = serializeJson(doc, buffer);
        
        // Send as HYPER_TCP_CMD_JSON_MESSAGE
        return sendCmd(HYPER_TCP_CMD_JSON_MESSAGE, 0, buffer, len);
    }

    // Send JSON message with string payload
    bool sendMessage(const char* targetId, const char* payloadJson) {
        if (_state != STATE_AUTHENTICATED) return false;
        
        // Create JSON document
        DynamicJsonDocument doc(512);
        doc["targetId"] = targetId;
        
        // Parse and add payload
        DynamicJsonDocument payloadDoc(256);
        deserializeJson(payloadDoc, payloadJson);
        doc["payload"] = payloadDoc;
        
        // Serialize to JSON string
        char buffer[512];
        size_t len = serializeJson(doc, buffer);
        
        // Send as HYPER_TCP_CMD_JSON_MESSAGE
        return sendCmd(HYPER_TCP_CMD_JSON_MESSAGE, 0, buffer, len);
    }

    // Send broadcast message to all connected clients
    bool broadcastMessage(JsonObject& payload) {
        if (_state != STATE_AUTHENTICATED) return false;
        
        // Create JSON document
        DynamicJsonDocument doc(512);
        doc["targetId"] = "broadcast";
        doc["payload"] = payload;
        
        // Serialize to JSON string
        char buffer[512];
        size_t len = serializeJson(doc, buffer);
        
        // Send as HYPER_TCP_CMD_BROADCAST
        return sendCmd(HYPER_TCP_CMD_BROADCAST, 0, buffer, len);
    }

    // Send message to server (const reference version)
    bool sendToServer(const JsonObject& payload) {
        if (_state != STATE_AUTHENTICATED) return false;
        
        // Create JSON document with server target
        DynamicJsonDocument doc(512);
        doc["targetId"] = "server";
        doc["payload"] = payload;
        
        // Serialize to JSON string
        char buffer[512];
        size_t len = serializeJson(doc, buffer);
        
        // Send as HYPER_TCP_CMD_JSON_MESSAGE
        return sendCmd(HYPER_TCP_CMD_JSON_MESSAGE, 0, buffer, len);
    }

    // Send message to server (non-const reference version for backward compatibility)
    bool sendToServer(JsonObject& payload) {
        return sendToServer(static_cast<const JsonObject&>(payload));
    }

private:
    bool sendCmd(uint8_t cmd, uint16_t id, const void* data, size_t length) {
        if (!_transport.connected()) return false;

        if (id == 0) {
            id = ++_msgId;
            if (_msgId == 0) _msgId = 1; // Skip 0
        }

        // Prepare header
        HyperTCPHeader header;
        header.type = cmd;
        header.msg_id = htons(id);
        header.length = htons(length);

        // Send header
        if (_transport.write(&header, sizeof(header)) != sizeof(header)) {
            return false;
        }

        // Send payload if any
        if (data && length > 0) {
            if (_transport.write(data, length) != length) {
                return false;
            }
        }

        return true;
    }

    bool sendLogin(const char* token) {
        return sendCmd(HYPER_TCP_CMD_LOGIN, 1, token, strlen(token));
    }

    bool waitForLoginResponse(uint32_t timeout) {
        unsigned long start = millis();
        while ((millis() - start) < timeout) {
            if (_transport.available() >= sizeof(HyperTCPHeader)) {
                HyperTCPHeader header;
                if (_transport.read(&header, sizeof(header)) == sizeof(header)) {
                    header.msg_id = ntohs(header.msg_id);
                    header.length = ntohs(header.length);
                    
                    // Check if this is the login response
                    if (header.type == HYPER_TCP_CMD_RESPONSE && header.msg_id == 1) {
                        // Read status
                        uint8_t status;
                        if (header.length == 1 && _transport.read(&status, 1) == 1) {
                            return (status == HYPER_TCP_STATUS_SUCCESS);
                        }
                    }
                }
                return false;
            }
            delay(10);
        }
        return false;
    }

    bool processInput() {
        // Read header
        HyperTCPHeader header;
        if (_transport.read(&header, sizeof(header)) != sizeof(header)) {
            return false;
        }

        header.type = header.type;
        header.msg_id = ntohs(header.msg_id);
        header.length = ntohs(header.length);

        // Handle different message types
        switch (header.type) {
            case HYPER_TCP_CMD_RESPONSE:
                // Handle response
                return true;
                
            case HYPER_TCP_CMD_PING:
                // Send pong response
                sendCmd(HYPER_TCP_CMD_RESPONSE, header.msg_id, NULL, 0);
                return true;
                
            case HYPER_TCP_CMD_JSON_MESSAGE: {
                // Handle JSON message
                if (header.length > 0) {
                    char* buffer = new char[header.length + 1];
                    if (_transport.read(buffer, header.length) == header.length) {
                        buffer[header.length] = '\0';
                        
                        // Parse JSON
                        DynamicJsonDocument doc(512);
                        DeserializationError error = deserializeJson(doc, buffer);
                        
                        if (!error) {
                            const char* from = doc["from"];
                            JsonObject payload = doc["payload"];
                            
                            if (from && !payload.isNull()) {
                                // Process received message
                                onMessageReceived(from, payload);
                            }
                        }
                    }
                    delete[] buffer;
                }
                sendCmd(HYPER_TCP_CMD_RESPONSE, header.msg_id, NULL, 0);
                return true;
            }
            
            case HYPER_TCP_CMD_BROADCAST: {
                // Handle broadcast message
                if (header.length > 0) {
                    char* buffer = new char[header.length + 1];
                    if (_transport.read(buffer, header.length) == header.length) {
                        buffer[header.length] = '\0';
                        
                        // Parse JSON
                        DynamicJsonDocument doc(512);
                        DeserializationError error = deserializeJson(doc, buffer);
                        
                        if (!error) {
                            const char* from = doc["from"];
                            JsonObject payload = doc["payload"];
                            
                            if (from && !payload.isNull()) {
                                // Process broadcast message
                                onBroadcastMessage(from, payload);
                            }
                        }
                    }
                    delete[] buffer;
                }
                sendCmd(HYPER_TCP_CMD_RESPONSE, header.msg_id, NULL, 0);
                return true;
            }
            
            case HYPER_TCP_CMD_REDIRECT: {
                // Handle server redirection
                if (header.length > 0) {
                    char* buffer = new char[header.length + 1];
                    if (_transport.read(buffer, header.length) == header.length) {
                        buffer[header.length] = '\0';
                        
                        // Parse redirection info
                        DynamicJsonDocument doc(256);
                        DeserializationError error = deserializeJson(doc, buffer);
                        
                        if (!error) {
                            const char* newServer = doc["server"];
                            uint16_t newPort = doc["port"] | 80;
                            
                            if (newServer) {
                                // Reconnect to new server
                                _transport.disconnect();
                                _transport.begin(newServer, newPort);
                                _state = STATE_CONNECTING;
                            }
                        }
                    }
                    delete[] buffer;
                }
                return true;
            }
            
            default:
                // Unknown command, just consume the payload
                if (header.length > 0) {
                    char dummy[256];
                    size_t toRead = header.length < sizeof(dummy) ? header.length : sizeof(dummy);
                    _transport.read(dummy, toRead);
                }
                return true;
        }
    }

    // Virtual methods for handling incoming messages
    virtual void onMessageReceived(const char* from, JsonObject& payload) {
        // Override in derived class to handle messages
        Serial.print("Message from: ");
        Serial.println(from);
        Serial.print("Payload: ");
        serializeJson(payload, Serial);
        Serial.println();
    }
    
    // Virtual method for handling broadcast messages
    virtual void onBroadcastMessage(const char* from, JsonObject& payload) {
        // Override in derived class to handle broadcast messages
        Serial.print("Broadcast from: ");
        Serial.println(from);
        Serial.print("Payload: ");
        serializeJson(payload, Serial);
        Serial.println();
    }

protected:
    Transport& _transport;
    ProtocolState _state;
    uint16_t _msgId;
};

#endif