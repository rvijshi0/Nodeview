# Endpoint Agent Implementation Plan: Raw Packet Injection & Sniffing

## 1. Prerequisites & System Architecture
The agent must run as a Windows Service or an elevated executable with **Administrative privileges** (`runas` manifest) to interact with low-level network drivers. It requires **Npcap** to bypass the native Windows TCP/IP stack restrictions on raw sockets.

### Dependencies
*   **Packet Capture Library:** Link against `wpcap.dll` and `Packet.dll` (via language-specific wrappers like `SharpPcap` for .NET, `gopacket` for Go, or native C/C++ Pcap headers).
*   **Orchestration Client:** Persistent bi-directional communication channel (WebSockets or long-polling HTTPS) to receive commands from and report data to the central dashboard.

---

## 2. Core Modules to Implement

### Module A: Driver & Environment Validation
Before executing any test, the agent must verify its execution environment.
*   **Driver Check:** Query the Windows Registry or Service Control Manager to ensure the Npcap service (`npcap`) is running.
*   **Privilege Check:** Ensure the process token has local administrative rights (`SeDebugPrivilege` / Elevated).
*   **Interface Mapping:** Enumerate all physical Network Interface Cards (NICs) to map their friendly names, local IP addresses, Subnet Masks, and hardware MAC addresses.

### Module B: Packet Crafting & Injection Engine (Source Mode)
When instructed by the dashboard to initiate a connectivity test, the agent must build and transmit a raw Layer 2 frame.

1.  **Command Payload Ingestion:** Accept three variables from the dashboard command:
    *   `Target_Destination_IP`
    *   `Spoofed_Source_IP`
    *   `Tracking_Token` (A unique 32-bit integer or hash for verification).
2.  **Route Resolution:** 
    *   Look up the local routing table to determine which local NIC handles the path to `Target_Destination_IP`.
    *   Determine the gateway MAC address (Next Hop) via the local ARP cache or send a rapid ARP request if missing.
3.  **Raw Buffer Construction:** Manually construct a continuous byte array matching network headers:
    *   **Ethernet Header (14 bytes):** Set Source MAC (local NIC), Destination MAC (Gateway/Next Hop), and EtherType (`0x0800` for IPv4).
    *   **IPv4 Header (20 bytes):** Set Version (`4`), TTL (`64`), Protocol (`6` for TCP). Set Source IP to the `Spoofed_Source_IP` provided by the dashboard. Set Destination IP to `Target_Destination_IP`. Compute the IPv4 Header Checksum.
    *   **TCP Header (20 bytes):** Set a pseudo-random Source Port. Set Destination Port (e.g., `443` or as requested). Set Flags to `SYN` (`0x02`). Set the **Sequence Number** field to match the `Tracking_Token`. Compute the TCP Checksum using the IPv4 pseudo-header.
4.  **Transmission:** Use Npcap's `pcap_sendpacket()` or `pcap_inject()` to send the raw buffer directly down to the network adapter, bypassing the Windows kernel stack.

### Module C: Packet Sniffing & Verification Engine (Destination Mode)
The agent must continuously or reactively scan incoming wire-level traffic for test packets without binding a standard socket to the port.

1.  **Capture Initialization:** Open the primary network interface using Npcap in non-promiscuous mode (or promiscuous if running on a mirrored port) with a small buffer timeout to minimize CPU overhead.
2.  **Kernel-Level Filtering:** Compile and apply a Berkeley Packet Filter (BPF) string to discard irrelevant traffic at the driver level:
    *   `tcp and dst port 443` (or dynamically match the target port requested).
3.  **Packet Parsing Loop:** For every frame matching the filter:
    *   Extract the IPv4 header and isolate the reported Source IP.
    *   Extract the TCP header and read the Sequence Number field.
    *   Match the Sequence Number against active or recent `Tracking_Token` values received from the dashboard.
4.  **Alerting & Callback:** The moment a signature match is confirmed, extract the packet's metadata (Timestamp, TTL value, Received Signal) and immediately dispatch a success payload back to the dashboard via the orchestration channel.

---

## 3. Installer & Deployment Strategy (The EXE Package)
To ship this agent as a single standalone executable that includes all features natively, build the following logic into the installation wrapper:

*   **Silent Npcap Bundling:** Include the official Npcap installer executable inside your agent installer assets.
*   **Installation Command:** Execute the Npcap installer silently during the agent setup phase using the silent deployment flags:
    ```cmd
    npcap-setup.exe /S /winpcap_mode=0 /loopback_support=0 /admin_only=1
    ```
    *(Note: `/winpcap_mode=0` ensures modern Npcap API features are used; `/admin_only=1` restricts driver access strictly to administrators for security hardening).*
*   **Service Registration:** Register your agent EXE to run as an automatic Windows Service (`Sc.exe create YourAgentName binPath= "..." start= auto`) running under the `NT AUTHORITY\SYSTEM` account to guarantee persistent network privileges across reboots.

---

## 4. Execution Workflow (Dashboard-to-Agent)

```text
[Dashboard] ───(1. Register Test: Token + Target)───> [Receiver Agent]
                                                            │ (Starts Sniffing)
[Dashboard] ───(2. Fire Test: Spoof IP + Target)─────> [Sender Agent]
                                                            │ (Injects Raw SYN)
                                                            v
                                                    [Network Fabric]
                                                            │
                                                            v
[Dashboard] <──(4. Match Reported Success)─────────── [Receiver Agent]
                                                              (Validates Token)