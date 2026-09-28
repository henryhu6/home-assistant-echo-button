export DEVELOPER_DIR := /Library/Developer/CommandLineTools
SDKROOT := /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk
CLANG := /Library/Developer/CommandLineTools/usr/bin/clang
CFLAGS := -fobjc-arc -Wall -Wextra -Werror -isysroot $(SDKROOT)
FRAMEWORKS := -framework Foundation -framework IOBluetooth

.PHONY: all clean

all: build/echo_button_probe

build/echo_button_probe: mac/echo_button_probe.m
	mkdir -p build
	$(CLANG) $(CFLAGS) $(FRAMEWORKS) $< -o $@

clean:
	rm -rf build
