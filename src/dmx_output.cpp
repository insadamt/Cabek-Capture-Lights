// Sends full DMX universes with explicit break/MAB timing and no UART0 access.
// Depends on Arduino GPIO/delays and ESP-IDF UART2; wiring: TX17, DE25, /RE26.
#include "dmx_output.h"

#include <Arduino.h>
#include <driver/uart.h>

namespace {
constexpr uart_port_t kDmxUart = UART_NUM_2;
constexpr int kTransmitPin = 17;
constexpr int kDriverEnablePin = 25;
constexpr int kReceiverDisablePin = 26;
constexpr uint32_t kDmxBaud = 250000;
constexpr unsigned kBreakMicroseconds = 120;
constexpr unsigned kMarkAfterBreakMicroseconds = 16;
constexpr size_t kUniverseSize = 513;
static_assert(kDmxUart != UART_NUM_0, "USB console UART must never carry DMX");
uint8_t universe[kUniverseSize] = {};
uint32_t completedFrames = 0;
uint32_t failures = 0;
bool initialized = false;

bool recordFailure(const char* operation, esp_err_t error) {
    ++failures;
    dmx::disableTransceiver();
    Serial0.printf("FAULT DMX %s: %s\n", operation, esp_err_to_name(error));
    return false;
}
}  // namespace

namespace dmx {
void disableTransceiver() {
    pinMode(kDriverEnablePin, OUTPUT);
    pinMode(kReceiverDisablePin, OUTPUT);
    digitalWrite(kDriverEnablePin, LOW);
    digitalWrite(kReceiverDisablePin, HIGH);
}

bool initialize() {
    // One owner per UART: do not call Serial2.begin() alongside this IDF driver.
    uart_config_t configuration = {};
    configuration.baud_rate = kDmxBaud;
    configuration.data_bits = UART_DATA_8_BITS;
    configuration.parity = UART_PARITY_DISABLE;
    configuration.stop_bits = UART_STOP_BITS_2;
    configuration.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    configuration.source_clk = UART_SCLK_APB;
    esp_err_t error = uart_param_config(kDmxUart, &configuration);
    if (error != ESP_OK) return recordFailure("configure", error);
    error = uart_set_pin(kDmxUart, kTransmitPin, UART_PIN_NO_CHANGE,
                         UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (error != ESP_OK) return recordFailure("pins", error);
    // A zero TX ring buffer keeps the static universe owned by this loop.
    error = uart_driver_install(kDmxUart, 256, 0, 0, nullptr, 0);
    if (error != ESP_OK) return recordFailure("driver", error);
    initialized = true;
    return true;
}

void setRgb(uint8_t red, uint8_t green, uint8_t blue) {
    universe[1] = red;
    universe[2] = green;
    universe[3] = blue;
}

bool transmitFrame() {
    if (!initialized) return recordFailure("not initialized", ESP_ERR_INVALID_STATE);
    // Invert an idle TX line for the leading break; never remap GPIO17 as GPIO.
    esp_err_t error = uart_set_line_inverse(kDmxUart, UART_SIGNAL_TXD_INV);
    if (error != ESP_OK) return recordFailure("break", error);
    digitalWrite(kDriverEnablePin, HIGH);
    delayMicroseconds(kBreakMicroseconds);
    error = uart_set_line_inverse(kDmxUart, 0);
    if (error != ESP_OK) return recordFailure("mark", error);
    delayMicroseconds(kMarkAfterBreakMicroseconds);
    const int written = uart_write_bytes(kDmxUart, universe, sizeof(universe));
    if (written != static_cast<int>(sizeof(universe))) {
        return recordFailure("write", ESP_FAIL);
    }
    // Wait through the final stop bits before changing TX polarity next frame.
    error = uart_wait_tx_done(kDmxUart, pdMS_TO_TICKS(100));
    if (error != ESP_OK) return recordFailure("drain", error);
    ++completedFrames;
    return true;
}

uint32_t sentFrames() { return completedFrames; }
uint32_t errorCount() { return failures; }
uint32_t baudRate() {
    uint32_t configuredBaud = 0;
    if (initialized) uart_get_baudrate(kDmxUart, &configuredBaud);
    return configuredBaud;
}
}  // namespace dmx
