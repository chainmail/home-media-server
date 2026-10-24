# Network Engineering Guide: Isolated Cluster Routing & Forwarding

- **Ripping host:** `192.168.1.32`
- **Gateway host, home-LAN address:** `192.168.1.251`
- **Gateway host, cluster address:** `192.168.45.1`
- **Home router:** `192.168.1.1`
- **Primary LAN subnet:** `192.168.1.0/24`
- **Isolated cluster subnet:** `192.168.45.0/24`
- **Target architecture:** Stateless PXE Talos node fleet

For the confirmed Fedora 44 gateway implementation and separate service examples, see [Gateway Services on Fedora 44](gateway-services-fedora44.md). This document describes the network design; it is not the Fedora service configuration.

---

## 1. Physical and Logical Networking Schematic
The gateway host routes traffic between the home LAN and the isolated cluster network. It is separate from the ripping host. DHCP, TFTP, Talos configuration serving, and the NFS export are available on its cluster-side address.


```text
[ Primary LAN: 192.168.1.0/24 ]
│
▼ (Gateway LAN interface: 192.168.1.251)
+-------------------------------------------------------+
| Gateway Host                                          |
| Routes between LAN and cluster; serves NFS, DHCP, TFTP|
+-------------------------------------------------------+
▲ (Gateway cluster interface: 192.168.45.1)
│
▼
[ Isolated Cluster Network: 192.168.45.0/24 ]
│
├──> [Talos Master Node: 192.168.45.10]
├──> [Talos Worker Node 1: 192.168.45.11]
└──> [Talos Worker Node X: 192.168.45.XX]

[Separate ripping host on home LAN: 192.168.1.32]
```


### 1.1 Interface Assignment
The gateway host has two network interfaces: `enp112s0` (`a4:ae:11:1e:78:d4`) on the home LAN at `192.168.1.251/24`, and `eno1` (altname `enp0s31f6`, MAC `a4:ae:11:1e:78:d3`) on the cluster network at `192.168.45.1/24`.

The ripping host remains a separate device at `192.168.1.32`.

---

## 2. Static Gateway Interface

Configure the gateway host with a default route through the home router (`192.168.1.1`) and a connected cluster route through `192.168.45.1`.

The gateway already has its confirmed NetworkManager interfaces: `enp112s0` (`192.168.1.251/24`) and `eno1` (`192.168.45.1/24`). Verify the active addresses with `ip -br address`; use the Fedora 44 gateway guide for service configuration.

---

## 3. IP Forwarding and Firewall Rules

Enable IP forwarding on the gateway host. Do not masquerade cluster traffic there: the home router has a return route for `192.168.45.0/24` via `192.168.1.251`, so local traffic can be routed directly. For internet access, ensure the home router's firewall and outbound NAT policy also permit the cluster subnet.

### 3.1 Persistent Kernel IP Forwarding Activation
Enable forwarding using the [gateway sysctl example](examples/fedora44-gateway/90-cluster-gateway.conf), then load it:

```bash
sudo sysctl --system
```

### 3.2 Firewall Forwarding Rules
The Fedora 44 gateway uses firewalld. Configure cluster-zone services and routed forwarding using the [Fedora gateway guide](gateway-services-fedora44.md). Do not add a `MASQUERADE` rule for `192.168.45.0/24` on the gateway.

---

## 4. DHCP and TFTP Service Isolation

Configure `dnsmasq` on the gateway host to listen only on `192.168.45.1`; this keeps cluster DHCP and PXE traffic off the home LAN. The standalone [dnsmasq example](examples/fedora44-gateway/dnsmasq-cluster.conf) is the service configuration for Fedora 44.

### 4.1 Updated `dnsmasq.conf` Tailored for the Isolated Network
The example assigns leases from `.45.50` through `.45.99`, advertises `.45.1` as the gateway and TFTP server, and deliberately does not set a boot filename until the Pi/Talos boot artifacts are verified.

---

## 5. Home Router Static Route

Add this static route on the home router at `192.168.1.1` so LAN devices can reach the cluster:

* **Destination network:** `192.168.45.0/24`
* **Next hop:** `192.168.1.251`

The ripping host at `192.168.1.32` uses the home router as usual; it does not act as the cluster gateway.
