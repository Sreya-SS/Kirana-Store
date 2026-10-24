/**
 * The ONE place to set where the backend lives.
 *
 * Your phone and laptop must be on the same WiFi. Put your laptop's LAN IP
 * here (NOT localhost / 127.0.0.1 -- that points at the phone itself).
 *
 * Find your laptop IP:
 *   Windows : ipconfig           -> "IPv4 Address" (e.g. 192.168.1.42)
 *   macOS   : ipconfig getifaddr en0
 *   Linux   : hostname -I
 *
 * Then set API_BASE_URL below and restart Expo.
 */
export const API_BASE_URL = 'http://127.0.0.1:8000';
