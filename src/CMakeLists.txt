idf_component_register(SRCS "main.c" "i2s_microphone.c" "telemetry.c" "fft_tdoa.c"
                       INCLUDE_DIRS "." "../include"
                       REQUIRES esp_driver_i2s esp_driver_gpio esp_timer driver)
