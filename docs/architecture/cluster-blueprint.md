# Cluster Blueprint

## Architectural Intent

This project describes a distributed video-transcoding cluster built from Raspberry Pi 5 nodes. It ingests DVD and Blu-ray rips, queues jobs through RabbitMQ, and distributes transcoding work across a Talos Linux Kubernetes cluster.

## Hardware Profile

- **Compute nodes:** 6 to 7 Raspberry Pi 5 boards with 8 GB or 16 GB RAM.
- **Power and storage:** PoE+ and M.2 NVMe combination boards, such as Waveshare PoE M.2 HAT+ or GeeekPi P33.
- **Storage media:** M.2 NVMe drives in a form factor supported by the selected board (2230, 2242, or 2280).
- **Power delivery:** A managed PoE+ switch with at least 150 W total power budget.
- **Thermal control:** Active cooling compatible with the selected combination board.

## Stateless PXE Provisioning

The nodes boot Talos Linux over the network. Configure the EEPROM to attempt network boot first:

```ini
BOOT_ORDER=0xf162
TFTP_PREFIX=0
```

The NVMe drives are reserved for Kubernetes runtime data (`/var/lib/containerd`, `/var/lib/kubelet`) and RabbitMQ state.

## Workload and Data Flow

- **Ingest:** A local system rips media to an NFS share on the NAS.
- **Queue:** A Python watchdog detects completed files and publishes jobs to RabbitMQ.
- **Transcode:** Headless `HandBrakeCLI` workers run software encoding on the Raspberry Pi 5 CPUs.
- **Autoscaling:** KEDA scales workers in response to queue depth, from zero to the configured maximum.

## Detailed Architecture Reference

- **Platform:** Raspberry Pi 5 cluster (6-7 nodes)
- **Operating system:** Talos Linux (stateless PXE boot)
- **Orchestration:** Kubernetes, RabbitMQ, and KEDA

---

## 1. System Topology and Automation Workflow
The cluster operates on a fully decoupled ingest, queue, and ephemeral process architecture. Individual stages are isolated to prevent network bottlenecks and eliminate disk-wear patterns.


```text
[DVD Ingest Node] ──────> [Central NAS (NFS File Storage)]
│
(Watchdog Trigger)
▼
[RabbitMQ Cluster] <───── [Python Queue Producer]
│
(KEDA Scale)
▼
[Talos K8s Nodes] ──────> [HandBrakeCLI Workers (RAM)] ──> [NAS Output Path]
(NVMe Cache Layer)
```


### 1.1 Step-by-Step Data Lifecycle
1. **Lossless Extraction:** The optical source is ripped to raw uncompressed `.mkv` files directly onto an NFS network export folder.
2. **Event Dispatch:** A background Python service detects the `IN_CLOSE_WRITE` file event flag, captures the target metadata, and submits an execution payload to a durable RabbitMQ queue.
3. **Cluster Activation:** KEDA intercepts the RabbitMQ metrics. If message depth > 0, it dynamically modifies the Kubernetes deployment replica state from `0` up to `7`.
4. **Network Streaming Transcode:** Pods read the raw block streams over NFS, convert them utilizing x264/x265 software libraries, and stream the finalized outputs directly back to the NAS destination.

---

## 2. Hardware Stack and Integration Constraints

### 2.1 The Raspberry Pi 5 SoC Architecture Change
Unlike previous generations, the Broadcom BCM2712 SoC on the Raspberry Pi 5 **does not feature hardware-accelerated H.264 or H.265 encoding blocks**. All transcoding tasks are processed via software execution threads utilizing the ARM Cortex-A76 CPU array. 

Due to a 2.5× structural performance increase per clock cycle over the Pi 4, a distributed cluster of 7 Pi 5 nodes executing software transcodes yields higher video quality density and smaller target file sizes than older generation hardware blocks.

### 2.2 Combo Expansion Hat Constraints
To consolidate infrastructure footprints, nodes are equipped with single integrated boards combining **IEEE 802.3at (PoE+)** extraction circuits alongside an **M.2 M-Key NVMe** interface slot.

*   **Thermal Control:** Continuous 100% CPU thread loading demands active heat dissipation. Combo boards must use open-frame designs accommodating the official Raspberry Pi active cooler or embed a high-static pressure cooling fan system capable of moving 3.5 CFM minimum.
*   **Power Delivery Calculations:** Peak load profiles (Cortex-A76 core max power + PCIe Gen 2/3 NVMe controller active reads) generate a draw variance between 14W and 18W per unit. The PoE switch backplane must guarantee a minimum overhead threshold of 25.5W per physical port (PoE+ standard).

---

## 3. Netboot (PXE) and In-Memory OS Deployment

Talos Linux runs as an immutable, stateless system directly inside volatile system RAM. Operating disks are entirely absent from the boot loop.

### 3.1 Onboard EEPROM Logic Parameters
Each node must be booted once via a standard evaluation environment to write persistence parameters directly into the bootloader SPI EEPROM non-volatile memory:

```ini
BOOT_ORDER=0xf162
TFTP_PREFIX=0
```
- `BOOT_ORDER=0xf162` tries network boot, then NVMe, then SD before restarting the sequence.
- `TFTP_PREFIX=0` uses the Raspberry Pi serial number as the TFTP directory prefix.

See the [Raspberry Pi bootloader documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#raspberry-pi-bootloader-configuration) for the `BOOT_ORDER` and `TFTP_PREFIX` settings.

### 3.2 Network Provisioning Layer
The infrastructure server requires two foundational configurations to stage the installation layer:

#### Dnsmasq DHCP/TFTP Mapping

Use the Fedora gateway's [dnsmasq example](../cluster-setup/examples/fedora44-gateway/dnsmasq-cluster.conf). It advertises the TFTP server but intentionally leaves the boot filename unset until the Raspberry Pi/Talos boot artifacts are verified.

#### TFTP Root and Boot Parameters

Populate `/var/lib/tftpboot` with the files required by the selected Raspberry Pi/Talos boot chain. With `TFTP_PREFIX=0`, the Pi firmware requests files under its serial-number directory. This repository does not yet contain a verified file list or `cmdline.txt` for that chain; use observed TFTP requests and the boot-asset generator's output rather than the earlier placeholder filenames.

The per-node kernel command line must set `talos.config` to the matching Nginx URL, such as `http://192.168.45.1/talos-configs/controlplane.yaml` or `http://192.168.45.1/talos-configs/worker-01.yaml`.

---

## 4. Storage Routing and Compute Parallelism

Because the operating system workspace initializes purely within RAM boundaries, the local combo NVMe drive is isolated entirely from operational software layers. It is treated as dedicated fast application storage.

### 4.1 Talos Persistent Volume Mapping Configuration
The machine configuration manifest overrides default runtime pathways, binding volatile container data engines directly to the NVMe block storage system:

```yaml
machine:
  storage:
    disks:
      - device: /dev/nvme0n1
        partitions:
          - mountpoint: /var/lib/containerd
          - mountpoint: /var/lib/kubelet
          - mountpoint: /var/mnt/storage
```
*   `/var/lib/containerd`: Eliminates network latency constraints during cluster image pulling phases by caching layers directly onto the M.2 NVMe silicon.
*   `/var/lib/kubelet`: Allocates scratchpads and ephemeral emptyDir volumes to local flash storage, keeping RAM dedicated to the transcoding runtime processes.
*   `/var/mnt/storage`: Creates a stable, high-speed physical partition layer dedicated exclusively to mounting persistent state metadata for the RabbitMQ cluster queue engine.
