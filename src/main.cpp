// Terminal-controlled RGB lighting and staged UART diagnostics for CABEK AI.
// Depends on Arduino Serial0, bounded RGB parsing, ESP32 clock/reset APIs and UART2 DMX.
#include <Arduino.h>
#include <esp_system.h>

#include "dmx_output.h"
#include "rgb_command.h"

#ifndef CABEK_DMX_STAGE
#define CABEK_DMX_STAGE 2
#endif

static_assert(CABEK_DMX_STAGE >= 0 && CABEK_DMX_STAGE <= 2, "Invalid DMX stage");

namespace {
constexpr char kFirmwareVersion[] = "cabek-dmx-v1";
constexpr const char* kMode = CABEK_DMX_STAGE == 0 ? "serial_only"
    : CABEK_DMX_STAGE == 1 ? "dmx_init" : "dmx_tx";
char selectedCommand = '0';
uint8_t selectedRed = 0;
uint8_t selectedGreen = 0;
uint8_t selectedBlue = 0;
bool outputHealthy = true;
lighting::RgbCommand rgbCommand;
uint32_t lastRgbByteAt = 0;

void printStatus() {
    Serial0.printf(
        "STATUS firmware=%s sketch=%s mode=%s command=%c rgb=%u,%u,%u "
        "protocol=rgb8-v1 frames=%lu errors=%lu heap=%lu min_heap=%lu uptime_ms=%lu "
        "uart0_baud=%lu uart2_baud=%lu xtal_mhz=%u reset=%u\n",
        kFirmwareVersion, ESP.getSketchMD5().c_str(), kMode, selectedCommand,
        selectedRed, selectedGreen, selectedBlue,
        static_cast<unsigned long>(dmx::sentFrames()),
        static_cast<unsigned long>(dmx::errorCount()),
        static_cast<unsigned long>(ESP.getFreeHeap()),
        static_cast<unsigned long>(ESP.getMinFreeHeap()), millis(),
        static_cast<unsigned long>(Serial0.baudRate()),
        static_cast<unsigned long>(dmx::baudRate()),
        static_cast<unsigned>(getXtalFrequencyMhz()),
        static_cast<unsigned>(esp_reset_reason()));
}

// ============================================================
// Extended packets never leak their digits into legacy commands.
// ============================================================
void receiveRgbByte(char character) {
    uint8_t channels[3] = {};
    bool complete = false;
    lastRgbByteAt = millis();
    const bool valid = rgbCommand.append(character, channels, complete);
    if (!complete || rgbCommand.expired()) return;
    if (!valid) {
        Serial0.println("ERR RGB: use R <0-255> <0-255> <0-255>");
        return;
    }
    if (!outputHealthy) {
        Serial0.println("ERR DMX unavailable: reset after checking diagnostics");
        return;
    }
    selectedCommand = 'R';
    selectedRed = channels[0];
    selectedGreen = channels[1];
    selectedBlue = channels[2];
    dmx::setRgb(selectedRed, selectedGreen, selectedBlue);
    Serial0.printf("OK R RGB %u %u %u\n", selectedRed, selectedGreen, selectedBlue);
}

void applyCommand(char command) {
    if (rgbCommand.active()) {
        receiveRgbByte(command);
        return;
    }
    if (command == 'R') {
        rgbCommand.begin();
        lastRgbByteAt = millis();
        return;
    }
    uint8_t red = 0;
    uint8_t green = 0;
    uint8_t blue = 0;
    const char* name = nullptr;
    switch (command) {
        case '0': name = "OFF"; break;
        case '1': name = "RED"; red = 255; break;
        case '2': name = "BLUE"; blue = 255; break;
        case '3': name = "GREEN"; green = 255; break;
        case '4': name = "WHITE"; red = green = blue = 255; break;
        case '?': printStatus(); return;
        case '\r': case '\n': case ' ': case '\t': return;
        default: Serial0.println("ERR command: use 0-4 or ?"); return;
    }
    if (!outputHealthy) {
        Serial0.println("ERR DMX unavailable: reset after checking diagnostics");
        return;
    }
    selectedCommand = command;
    selectedRed = red;
    selectedGreen = green;
    selectedBlue = blue;
    dmx::setRgb(red, green, blue);
    Serial0.printf("OK %c %s %u %u %u\n", command, name, red, green, blue);
}
}  // namespace

void setup() {
    // Explicit UART0 pins prevent board defaults or aliases from moving USB I/O.
    // APB avoids the coarse 1 MHz REF_TICK divider used by Arduino's default.
    const bool consoleClockConfigured = Serial0.setClockSource(UART_CLK_SRC_APB);
    Serial0.begin(115200, SERIAL_8N1, 3, 1);
    delay(250);
    Serial0.printf("BOOT firmware=%s sketch=%s mode=%s sdk=%s cpu_mhz=%u\n",
                   kFirmwareVersion, ESP.getSketchMD5().c_str(), kMode,
                   ESP.getSdkVersion(), static_cast<unsigned>(getCpuFrequencyMhz()));
    dmx::disableTransceiver();
    if (!consoleClockConfigured) {
        outputHealthy = false;
        Serial0.println("FAULT UART0 clock configuration failed");
    }
    if (CABEK_DMX_STAGE > 0 && outputHealthy) {
        outputHealthy = dmx::initialize();
    }
    Serial0.println(outputHealthy ? "READY 0=OFF 1=RED 2=BLUE 3=GREEN 4=WHITE ?=STATUS"
                                 : "FAULT DMX initialization failed");
    printStatus();
}

void loop() {
    if (rgbCommand.active() && !rgbCommand.expired() && static_cast<uint32_t>(millis() - lastRgbByteAt) > 250) {
        // Drain to newline after timeout so delayed payload digits cannot select legacy colors.
        rgbCommand.expire();
        Serial0.println("ERR RGB timeout");
    }
    // Bound input work so a pasted command stream cannot starve DMX refresh.
    for (unsigned processed = 0; processed < 32 && Serial0.available() > 0; ++processed) {
        applyCommand(static_cast<char>(Serial0.read()));
    }
    if (CABEK_DMX_STAGE == 2 && outputHealthy) {
        outputHealthy = dmx::transmitFrame();
    }
    delay(2);
}
