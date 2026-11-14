// Verify packet bounds and atomic validation without an ESP32 or LEDs.
// Depends on the firmware's pure RGB parser and the native C++ standard library.
#include <cassert>
#include <cstring>
#include <initializer_list>
#include "../src/rgb_command.h"

bool parse(const char* packet, uint8_t (&channels)[3]) {
    lighting::RgbCommand parser;
    parser.begin();
    bool complete = false;
    bool valid = false;
    for (unsigned index = 0; index < strlen(packet); ++index) {
        valid = parser.append(packet[index], channels, complete);
    }
    assert(complete);
    assert(!parser.active());
    return valid;
}

int main() {
    uint8_t channels[3] = {};
    assert(parse(" 0 128 255\n", channels));
    assert(channels[0] == 0 && channels[1] == 128 && channels[2] == 255);
    assert(parse(" 255 1 0\r\n", channels));
    for (const char* packet : {" 256 0 0\n", " -1 0 0\n", " 0 1\n", " 0 1 2 3\n",
                               "0 1 2\n", " 0.5 0 0\n", " 999999999999999999999999999999999 0 0\n"}) {
        assert(!parse(packet, channels));
    }
    lighting::RgbCommand parser;
    parser.begin();
    parser.expire();
    assert(parser.active() && parser.expired());
    bool complete = false;
    assert(!parser.append('1', channels, complete));
    assert(!parser.append('\n', channels, complete));
    assert(complete && !parser.active());
    parser.begin();
    parser.cancel();
    assert(!parser.active());
}
