Почему через ssh все работает а через веб панель нет?
Пример:

> AdGuard VPN v1.7.12 is now available
You can update to the latest version by running `adguardvpn-cli update`
/ # Connection to 192.168.1.1 closed by remote host.
Connection to 192.168.1.1 closed.
PS C:\Users\Richm> ssh 192.168.1.1 -l admin
admin@192.168.1.1's password:
Permission denied, please try again.
admin@192.168.1.1's password:
KeeneticOS version 5.00.C.8.0-1, copyright (c) 2010-2026 Keenetic Ltd.


This software is a subject of Keenetic Ltd. end-user licence agreement. By using it you agree on terms and conditions
hereof. For more information please check https://keenetic.com/legal

(config)> exeec sh
Command::Base error[7405600]: no such command: exeec.
(config)> exec sh


BusyBox v1.37.0 (2025-06-01 14:50:09 UTC) built-in shell (ash)

/ # adguardvpn-cli list-locations\
> ^C

/ # adguardvpn-cli list-locations
ISO   COUNTRY              CITY                           PING ESTIMATE
SE    Sweden               Stockholm                      24
EE    Estonia              Tallinn                        26
FI    Finland              Helsinki                       34
LV    Latvia               Riga                           35
DK    Denmark              Copenhagen                     38
DE    Germany              Frankfurt                      42
DE    Germany              Berlin                         43
BE    Belgium              Brussels                       44
AT    Austria              Vienna                         48
CH    Switzerland          Zurich                         49
NL    Netherlands          Amsterdam                      49
LU    Luxembourg           Luxembourg                     50
IT    Italy                Milan                          51
GB    United Kingdom       London                         52
FR    France               Paris                          52
LT    Lithuania            Vilnius                        54
PL    Poland               Warsaw                         56
IT    Italy                Rome                           59
ES    Spain                Barcelona                      65
EG    Egypt                Cairo                          66
RS    Serbia               Belgrade                       66
ES    Spain                Madrid                         66
MD    Moldova              Chișinău                       67
GB    United Kingdom       Manchester                     67
BG    Bulgaria             Sofia                          69
CZ    Czechia              Prague                         74
HR    Croatia              Zagreb                         74
HU    Hungary              Budapest                       75
IS    Iceland              Reykjavik                      75
UA    Ukraine              Kyiv                           75
NO    Norway               Oslo                           75
RO    Romania              Bucharest                      76
TR    Turkey               Istanbul                       77
GR    Greece               Athens                         77
IE    Ireland              Dublin                         81
CY    Cyprus               Nicosia                        82
SK    Slovakia             Bratislava                     83
PT    Portugal             Lisbon                         85
FR    France               Marseille                      90
US    United States        New York                       112
US    United States        Boston                         114
IT    Italy                Palermo                        115
IL    Israel               Tel Aviv                       119
RU    Russia               Moscow (Virtual)               126
US    United States        Atlanta                        131
CA    Canada               Toronto                        132
CA    Canada               Montreal                       136
US    United States        Denver                         139
US    United States        Chicago                        142
US    United States        Miami                          145
AE    UAE                  Dubai                          151
NG    Nigeria              Lagos                          153
US    United States        Dallas                         155
MX    Mexico               Mexico City                    169
US    United States        Seattle                        173
US    United States        Phoenix                        177
US    United States        Las Vegas                      178
CA    Canada               Vancouver                      179
US    United States        Los Angeles                    190
KH    Cambodia             Phnom Penh                     193
US    United States        Silicon Valley                 194
ZA    South Africa         Johannesburg                   197
ID    Indonesia            Jakarta                        199
TW    Taiwan               Taipei                         200
NP    Nepal                Kathmandu                      201
SG    Singapore            Singapore                      202
VN    Vietnam              Hanoi                          205
IN    India                Mumbai (Virtual)               210
PE    Peru                 Lima                           217
PH    Philippines          Manila                         220
CN    China                Shanghai (Virtual)             228
TH    Thailand             Bangkok                        228
HK    Hong Kong            Hong Kong                      230
KZ    Kazakhstan           Astana                         244
BR    Brazil               São Paulo                      247
CO    Colombia             Bogota                         257
AR    Argentina            Buenos Aires                   274
KR    South Korea          Seoul                          277
JP    Japan                Tokyo                          279
CL    Chile                Santiago                       297
AU    Australia            Sydney                         320
NZ    New Zealand          Auckland                       321

You can connect to a location by running `adguardvpn-cli connect -l 'city, country or ISO code'`

> AdGuard VPN v1.7.12 is now available
You can update to the latest version by running `adguardvpn-cli update`
/ # adguardvpn-cli connect Sweden
The following argument was not expected: Sweden
connect
  Connect to AdGuard VPN
  Options:
    -l,--location TEXT          Location to connect to (city name, country name, or ISO code). By default, AdGuard VPN connects to the last used location
    -f,--fastest                Connect to the fastest available location
    -v,--verbose                Show log from VPN service
    --no-fork                   Do not fork the VPN service to the background
    --ppid-file TEXT            File for writing parent process ID
    --pid-file TEXT             File for writing process ID
    -y,--yes                    Automatic answering 'yes' to all questions
    -4,--ipv4only               Force the application to connect only to IPv4 servers
    -6,--ipv6only               Force the application to connect only to IPv6 servers
    --log-to-file               Redirect process output to file when --no-fork flag is used
    --no-progress               Do not show styled log progress when --no-fork flag is not used
    --boot                      Automatically and indefinitely retries connection
/ # adguardvpn-cli connect -l Sweden
Disconnecting from current location to connect elsewhere...
07.04.2026 19:22:07.112173 INFO  [4067] VPNCORE vpn_listen: [2] Done
07.04.2026 19:22:07.127099 ERROR [18921] UDP_SOCKET udp_socket_create_inner: [] [id=6900/[2a02:6ea0:c51b::7]:443] Faile
07.04.2026 19:22:07.143052 ERROR [18921] UDP_SOCKET udp_socket_create_inner: [] [id=6902/[2a02:6ea0:c51b::6]:443] Faile
07.04.2026 19:22:07.143052 ERROR [18921] UDP_SOCKET udp_socket_create_inner: [] [id=6902/[2a02:6ea0:c51b::6]:443] Faile
07.04.2026 19:22:08.018972 INFO  [18921] VPNCORE pinger_handler: [2] Using endpoint: name=y1sqvl.ubuntu.com, address=14
Successfully Connected to STOCKHOLM
You are now connected. You can check the connection status by running `adguardvpn-cli status`

> AdGuard VPN v1.7.12 is now available
You can update to the latest version by running `adguardvpn-cli update`
/ # Connection to 192.168.1.1 closed by remote host.
Connection to 192.168.1.1 closed.

Вот что получается при нажатии на кнопку "Обновить локации":
CLI: доступен
Локаций найдено: 0
Сообщение: Команда завершилась с ошибкой.

Вот что получается при нажатии на кнопку "Обновить статус":
CLI: доступен
Команда: adguardvpn-cli status
Статус: не подключено
Локация: не определена
Сообщение: Команда завершилась с ошибкой.

Результат последней операции:
Переключение завершено.

{
  "success": false,
  "message": "Скрипт завершился с ошибкой.",
  "executed_at": "2026-04-07T19:20:21.723990+00:00",
  "stdout": "",
  "stderr": "",
  "returncode": 1,
  "command": [
    "sh",
    "/opt/share/keenetic-vpn-panel/generated/adguardvpn-rotate.sh"
  ]
}

Вот логи:
2026-04-07 22:20:21 ERROR: could not get locations list
2026-04-07 22:20:21 FAILED: resource unreachable via HELSINKI
2026-04-07 22:20:21 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 22:20:16 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 22:20:08 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 22:19:55 Trying location: HELSINKI
2026-04-07 22:19:55 Trying last known good location: HELSINKI
2026-04-07 22:19:55 FAIL: resource unreachable, starting location rotation
2026-04-07 22:19:55 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 22:19:47 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 22:19:42 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:56:03 ERROR: could not get locations list
2026-04-07 06:56:03 FAILED: resource unreachable via HELSINKI
2026-04-07 06:56:03 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:55:58 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:55:53 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:55:40 Trying location: HELSINKI
2026-04-07 06:55:40 Trying last known good location: HELSINKI
2026-04-07 06:55:40 FAIL: resource unreachable, starting location rotation
2026-04-07 06:55:40 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:55:35 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:55:29 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:19:52 ERROR: could not get locations list
2026-04-07 06:19:52 FAILED: resource unreachable via HELSINKI
2026-04-07 06:19:52 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:19:47 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:19:41 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:19:28 Trying location: HELSINKI
2026-04-07 06:19:28 Trying last known good location: HELSINKI
2026-04-07 06:19:28 FAIL: resource unreachable, starting location rotation
2026-04-07 06:19:28 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:19:23 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:19:18 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:16:05 ERROR: could not get locations list
2026-04-07 06:16:04 FAILED: resource unreachable via HELSINKI
2026-04-07 06:15:00 Trying location: HELSINKI
2026-04-07 06:15:00 Trying last known good location: HELSINKI
2026-04-07 06:15:00 FAIL: resource unreachable, starting location rotation
2026-04-07 06:13:47 ERROR: could not get locations list
2026-04-07 06:13:47 FAILED: resource unreachable via HELSINKI
2026-04-07 06:13:47 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:13:42 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:13:37 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:13:24 Trying location: HELSINKI
2026-04-07 06:13:24 Trying last known good location: HELSINKI
2026-04-07 06:13:24 FAIL: resource unreachable, starting location rotation
2026-04-07 06:13:24 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:13:19 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:13:13 HTTP check failed: url=https://web.telegram.org/k/ code=000
2026-04-07 06:10:54 ERROR: could not get locations list
2026-04-07 06:10:54 FAILED: resource unreachable via HELSINKI
2026-04-07 06:10:08 Trying location: HELSINKI
2026-04-07 06:10:08 Trying last known good location: HELSINKI
2026-04-07 06:10:08 FAIL: resource unreachable, starting location rotation
2026-04-07 06:05:01 OK: resource reachable, no switch needed
2026-04-07 06:00:01 OK: resource reachable, no switch needed
2026-04-07 05:55:01 OK: resource reachable, no switch needed
2026-04-07 05:50:01 OK: resource reachable, no switch needed
2026-04-07 05:45:01 OK: resource reachable, no switch needed
2026-04-07 05:40:01 OK: resource reachable, no switch needed
2026-04-07 05:35:01 OK: resource reachable, no switch needed
2026-04-07 05:30:01 OK: resource reachable, no switch needed
2026-04-07 05:25:01 OK: resource reachable, no switch needed
2026-04-07 05:20:01 OK: resource reachable, no switch needed
2026-04-07 05:15:02 OK: resource reachable, no switch needed
2026-04-07 05:10:01 OK: resource reachable, no switch needed
2026-04-07 05:05:01 OK: resource reachable, no switch needed
2026-04-07 05:00:01 OK: resource reachable, no switch needed
2026-04-07 04:55:01 OK: resource reachable, no switch needed
2026-04-07 04:50:01 OK: resource reachable, no switch needed
2026-04-07 04:45:01 OK: resource reachable, no switch needed