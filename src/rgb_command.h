// Parse bounded RGB commands without allocation or touching hardware.
// Depends only on integer types; shared by the ESP32 console and native tests.
#pragma once

#include <stdint.h>

namespace lighting {
class RgbCommand {
public:
    void begin() { active_ = true; length_ = 0; invalid_ = false; expired_ = false; }
    bool active() const { return active_; }
    void cancel() { active_ = false; }
    void expire() { invalid_ = true; expired_ = true; }
    bool expired() const { return expired_; }

    bool append(char character, uint8_t (&channels)[3], bool& complete) {
        complete = character == '\n';
        if (!complete) {
            if (length_ < sizeof(buffer_)) buffer_[length_++] = character;
            else invalid_ = true;
            return false;
        }
        active_ = false;
        if (invalid_) return false;
        unsigned cursor = 0;
        for (unsigned index = 0; index < 3; ++index) {
            const unsigned beforeSpace = cursor;
            while (cursor < length_ && (buffer_[cursor] == ' ' || buffer_[cursor] == '\t')) ++cursor;
            if (cursor == beforeSpace) return false;
            unsigned value = 0;
            unsigned digits = 0;
            while (cursor < length_ && buffer_[cursor] >= '0' && buffer_[cursor] <= '9') {
                value = value * 10 + static_cast<unsigned>(buffer_[cursor++] - '0');
                if (++digits > 3 || value > 255) return false;
            }
            if (!digits) return false;
            channels[index] = static_cast<uint8_t>(value);
        }
        while (cursor < length_ && (buffer_[cursor] == ' ' || buffer_[cursor] == '\t'
                                   || buffer_[cursor] == '\r')) ++cursor;
        return cursor == length_;
    }

private:
    char buffer_[32] = {};
    unsigned length_ = 0;
    bool active_ = false;
    bool invalid_ = false;
    bool expired_ = false;
};
}  // namespace lighting
