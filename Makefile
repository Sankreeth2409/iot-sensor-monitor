PY ?= python3

.PHONY: test demo evaluate sensor
test:
	$(PY) -m unittest discover -v
demo:
	$(PY) -m iot_monitor demo
evaluate:
	$(PY) -m iot_monitor evaluate
sensor: build/sensor
build/sensor: c/sensor.c
	mkdir -p build && cc -std=c99 -O2 -Wall -Wextra c/sensor.c -o $@ -lm
