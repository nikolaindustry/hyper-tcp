/*
 * HyperTCP Protocol Example
 * Demonstrates device-to-server and device-to-device communication
 * Updated with new features
 */

#include "HyperTCPProtocol.h"
#include <WiFi.h>

// WiFi credentials
const char* ssid = "your_wifi_ssid";
const char* password = "your_wifi_password";

// Server details - Updated for your network
const char* server = "192.168.31.85";  // Your computer's IP address
const uint16_t port = 8080;

// Authentication token
const char* authToken = "your_auth_token_here";

// WiFi client
WiFiClient wifiClient;

// HyperTCP transport and protocol
HyperTCPTransport<WiFiClient> myTransport(wifiClient);
HyperTCPProtocol<HyperTCPTransport<WiFiClient>> myProtocol(myTransport);

// LED pin for demonstration
const int ledPin = 2;
// Additional pins for more features
const int buttonPin = 0;  // Button to trigger events

// Device ID for identification
const char* deviceId = "esp32_sensor_001";

// Connection status tracking
bool isConnected = false;
unsigned long lastReconnectAttempt = 0;
const unsigned long reconnectInterval = 5000;  // 5 seconds

void setup() {
  Serial.begin(115200);
  
  // Initialize LED and button
  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, LOW);
  pinMode(buttonPin, INPUT_PULLUP);
  
  // Connect to WiFi
  Serial.print("Connecting to WiFi...");
  WiFi.begin(ssid, password);
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  
  Serial.println("WiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
  
  // Connect to HyperTCP server
  connectToServer();
}

void connectToServer() {
  Serial.print("Connecting to HyperTCP server at ");
  Serial.print(server);
  Serial.print(":");
  Serial.println(port);
  
  // Create login data with device ID for better identification
  StaticJsonDocument<200> loginData;
  loginData["token"] = authToken;
  loginData["device_id"] = deviceId;
  
  // Connect with enhanced login data
  if (myProtocol.connect(authToken, server, port)) {
    Serial.println("Connected!");
    digitalWrite(ledPin, HIGH);  // Turn on LED to indicate connection
    isConnected = true;
    lastReconnectAttempt = millis();
    
    // Send initial connection status
    sendConnectionStatus(true);
  } else {
    Serial.println("Failed to connect!");
    isConnected = false;
  }
}

void loop() {
  // Run the HyperTCP protocol
  if (myProtocol.run()) {
    isConnected = true;
    
    // Send periodic sensor data
    static unsigned long lastSensorUpdate = 0;
    if (millis() - lastSensorUpdate > 10000) {  // Every 10 seconds
      sendSensorData();
      lastSensorUpdate = millis();
    }
    
    // Check for button press to send event
    static bool lastButtonState = true;  // Button is pulled up, so default is HIGH
    bool buttonState = digitalRead(buttonPin);
    
    // Detect button press (transition from HIGH to LOW)
    if (lastButtonState && !buttonState) {
      sendButtonPressEvent();
    }
    lastButtonState = buttonState;
    
    // Send periodic heartbeat
    static unsigned long lastHeartbeat = 0;
    if (millis() - lastHeartbeat > 30000) {  // Every 30 seconds
      sendHeartbeat();
      lastHeartbeat = millis();
    }
  } else {
    // Connection lost, try to reconnect
    isConnected = false;
    Serial.println("Connection lost, attempting to reconnect...");
    digitalWrite(ledPin, LOW);  // Turn off LED
    
    // Implement backoff strategy for reconnection
    if (millis() - lastReconnectAttempt > reconnectInterval) {
      if (myProtocol.connect(authToken, server, port)) {
        Serial.println("Reconnected!");
        digitalWrite(ledPin, HIGH);  // Turn on LED
        isConnected = true;
        lastReconnectAttempt = millis();
        
        // Send reconnection status
        sendConnectionStatus(true);
      } else {
        Serial.println("Reconnection failed!");
        lastReconnectAttempt = millis();
      }
    }
  }
  
  delay(100);
}

// Send sensor data (simulated)
void sendSensorData() {
  // Create sensor data
  StaticJsonDocument<300> sensorData;
  sensorData["command"] = "sensor_data";
  sensorData["device_id"] = deviceId;
  sensorData["temperature"] = random(20, 30);
  sensorData["humidity"] = random(40, 60);
  sensorData["light"] = analogRead(34);  // Read from light sensor pin
  sensorData["timestamp"] = millis();
  
  // Send to server
  if (myProtocol.sendToServer(sensorData.as<JsonObject>())) {
    Serial.println("Sensor data sent successfully");
  } else {
    Serial.println("Failed to send sensor data");
  }
}

// Send button press event
void sendButtonPressEvent() {
  StaticJsonDocument<200> eventData;
  eventData["command"] = "button_press";
  eventData["device_id"] = deviceId;
  eventData["timestamp"] = millis();
  
  if (myProtocol.sendToServer(eventData.as<JsonObject>())) {
    Serial.println("Button press event sent");
    
    // Flash LED to indicate event sent
    for (int i = 0; i < 2; i++) {
      digitalWrite(ledPin, LOW);
      delay(100);
      digitalWrite(ledPin, HIGH);
      delay(100);
    }
  } else {
    Serial.println("Failed to send button press event");
  }
}

// Send heartbeat to indicate device is alive
void sendHeartbeat() {
  StaticJsonDocument<150> heartbeatData;
  heartbeatData["command"] = "heartbeat";
  heartbeatData["device_id"] = deviceId;
  heartbeatData["uptime"] = millis() / 1000;  // Uptime in seconds
  
  if (myProtocol.sendToServer(heartbeatData.as<JsonObject>())) {
    Serial.println("Heartbeat sent");
  } else {
    Serial.println("Failed to send heartbeat");
  }
}

// Send connection status update
void sendConnectionStatus(bool connected) {
  StaticJsonDocument<200> statusData;
  statusData["command"] = "connection_status";
  statusData["device_id"] = deviceId;
  statusData["status"] = connected ? "connected" : "disconnected";
  statusData["timestamp"] = millis();
  
  if (myProtocol.sendToServer(statusData.as<JsonObject>())) {
    Serial.println("Connection status sent");
  } else {
    Serial.println("Failed to send connection status");
  }
}

// Handle incoming messages
class MyProtocolWithHandlers : public HyperTCPProtocol<HyperTCPTransport<WiFiClient>> {
public:
    MyProtocolWithHandlers(HyperTCPTransport<WiFiClient>& transport) 
        : HyperTCPProtocol<HyperTCPTransport<WiFiClient>>(transport) {}

    void onMessageReceived(const char* from, JsonObject& payload) override {
        Serial.print("Message from: ");
        Serial.println(from);
        Serial.print("Payload: ");
        serializeJson(payload, Serial);
        Serial.println();
        
        // Handle specific commands
        const char* command = payload["command"];
        if (command) {
            if (strcmp(command, "control") == 0) {
                handleControlCommand(payload);
            } else if (strcmp(command, "ping") == 0) {
                handlePingCommand(payload);
            } else if (strcmp(command, "config") == 0) {
                handleConfigCommand(payload);
            } else if (strcmp(command, "ota_update") == 0) {
                handleOTAUpdateCommand(payload);
            }
        }
    }
    
    void onBroadcastMessage(const char* from, JsonObject& payload) override {
        Serial.print("Broadcast from: ");
        Serial.println(from);
        Serial.print("Payload: ");
        serializeJson(payload, Serial);
        Serial.println();
        
        // Handle broadcast messages
        const char* command = payload["command"];
        if (command) {
            if (strcmp(command, "notification") == 0) {
                handleNotification(payload);
            } else if (strcmp(command, "firmware_update") == 0) {
                handleFirmwareUpdate(payload);
            } else if (strcmp(command, "system_command") == 0) {
                handleSystemCommand(payload);
            }
        }
    }

private:
    void handleControlCommand(JsonObject& payload) {
        const char* device = payload["device"];
        const char* action = payload["action"];
        int value = payload["value"];
        
        Serial.print("Control command: ");
        Serial.print(device);
        Serial.print(" ");
        Serial.print(action);
        Serial.print(" ");
        Serial.println(value);
        
        // Execute control command
        if (strcmp(device, "led") == 0) {
            if (strcmp(action, "toggle") == 0) {
                digitalWrite(ledPin, !digitalRead(ledPin));
            } else if (strcmp(action, "on") == 0) {
                digitalWrite(ledPin, HIGH);
            } else if (strcmp(action, "off") == 0) {
                digitalWrite(ledPin, LOW);
            } else if (strcmp(action, "blink") == 0) {
                // Blink LED specified number of times
                for (int i = 0; i < value; i++) {
                    digitalWrite(ledPin, HIGH);
                    delay(200);
                    digitalWrite(ledPin, LOW);
                    delay(200);
                }
                digitalWrite(ledPin, HIGH);  // Restore LED state
            }
        }
        
        // Send acknowledgment
        StaticJsonDocument<150> ack;
        ack["command"] = "ack";
        ack["message"] = "Command executed";
        ack["device"] = device;
        ack["action"] = action;
        sendToServer(ack.as<JsonObject>());
    }
    
    void handlePingCommand(JsonObject& payload) {
        Serial.println("Ping received, sending pong...");
        
        // Send pong response
        StaticJsonDocument<150> pong;
        pong["command"] = "pong";
        pong["timestamp"] = millis();
        pong["device_id"] = deviceId;
        sendToServer(pong.as<JsonObject>());
    }
    
    void handleNotification(JsonObject& payload) {
        const char* message = payload["message"];
        Serial.print("Notification: ");
        Serial.println(message);
        
        // Flash LED to indicate notification
        for (int i = 0; i < 3; i++) {
            digitalWrite(ledPin, LOW);
            delay(200);
            digitalWrite(ledPin, HIGH);
            delay(200);
        }
        digitalWrite(ledPin, HIGH);  // Restore LED state
    }
    
    void handleConfigCommand(JsonObject& payload) {
        Serial.println("Configuration command received");
        
        // Handle configuration updates
        if (payload.containsKey("sampling_rate")) {
            int rate = payload["sampling_rate"];
            Serial.print("Setting sampling rate to: ");
            Serial.println(rate);
        }
        
        if (payload.containsKey("reporting_interval")) {
            int interval = payload["reporting_interval"];
            Serial.print("Setting reporting interval to: ");
            Serial.println(interval);
        }
        
        // Send acknowledgment
        StaticJsonDocument<150> ack;
        ack["command"] = "config_ack";
        ack["message"] = "Configuration updated";
        sendToServer(ack.as<JsonObject>());
    }
    
    void handleOTAUpdateCommand(JsonObject& payload) {
        const char* version = payload["version"];
        const char* url = payload["url"];
        
        Serial.print("OTA update requested. Version: ");
        Serial.print(version);
        Serial.print(", URL: ");
        Serial.println(url);
        
        // Send acknowledgment
        StaticJsonDocument<150> ack;
        ack["command"] = "ota_ack";
        ack["message"] = "OTA update initiated";
        ack["version"] = version;
        sendToServer(ack.as<JsonObject>());
        
        // In a real implementation, you would start the OTA update process here
        // For now, we'll just simulate it with LED blinking
        for (int i = 0; i < 5; i++) {
            digitalWrite(ledPin, LOW);
            delay(500);
            digitalWrite(ledPin, HIGH);
            delay(500);
        }
    }
    
    void handleFirmwareUpdate(JsonObject& payload) {
        const char* version = payload["version"];
        Serial.print("Firmware update notification. Version: ");
        Serial.println(version);
        
        // Flash LED rapidly to indicate firmware update
        for (int i = 0; i < 10; i++) {
            digitalWrite(ledPin, LOW);
            delay(100);
            digitalWrite(ledPin, HIGH);
            delay(100);
        }
        digitalWrite(ledPin, HIGH);  // Restore LED state
    }
    
    void handleSystemCommand(JsonObject& payload) {
        const char* action = payload["action"];
        Serial.print("System command received: ");
        Serial.println(action);
        
        if (strcmp(action, "reboot") == 0) {
            Serial.println("Rebooting device...");
            // Send acknowledgment before rebooting
            StaticJsonDocument<100> ack;
            ack["command"] = "system_ack";
            ack["message"] = "Rebooting";
            sendToServer(ack.as<JsonObject>());
            
            // In a real implementation, you would reboot the device here
            // ESP.restart();
        } else if (strcmp(action, "reset") == 0) {
            Serial.println("Resetting device...");
            // Send acknowledgment
            StaticJsonDocument<100> ack;
            ack["command"] = "system_ack";
            ack["message"] = "Resetting";
            sendToServer(ack.as<JsonObject>());
            
            // In a real implementation, you would reset the device here
        }
    }
};

// Create instance with handlers
MyProtocolWithHandlers myProtocolWithHandlers(myTransport);