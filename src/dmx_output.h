// UART2-only DMX output contract; keeps USB UART0 outside the DMX driver.
// Depends on fixed-size integer types; implementation uses ESP-IDF's public UART API.
#pragma once

#include <stdint.h>

namespace dmx {
void disableTransceiver();
bool initialize();
void setRgb(uint8_t red, uint8_t green, uint8_t blue);
bool transmitFrame();
uint32_t sentFrames();
uint32_t errorCount();
uint32_t baudRate();
}  // namespace dmx
