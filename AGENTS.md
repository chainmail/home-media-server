# Session Context Log: Distributed Transcoding Cluster

## 1. Architectural Intent
The goal of this project is to build an automated, distributed video transcoding cluster using a fleet of Raspberry Pi 5 single-board computers. The system ingests raw DVD and Blu-ray rips, manages job ordering via an enterprise message queue, and distributes processing workloads dynamically across an immutable Kubernetes cluster.

## 2. Hardware Profile Matrix
*   **Compute Nodes:** 6 to 7 × Raspberry Pi 5 (8GB or 16GB RAM variants).
*   **Power & Storage Interface:** Unified combo boards combining IEEE 802.3at (PoE+) input with an M.2 NVMe expansion slot (e.g., Waveshare PoE M.2 HAT+ or GeeekPi P33).
*   **Storage Media:** High-end M.2 NVMe Solid State Drives (Form Factor 2230/2242/2280).
*   **Power Delivery:** Managed PoE+ Network Switch with a guaranteed minimum total power budget of 150W.
*   **Thermal Control:** Active cooling via dedicated heatsink fans compatible with the combo hat design layout.

## 3. Provisioning Strategy (Stateless PXE Boot)
To ensure absolute resilience against storage corruption, the nodes use a stateless PXE network boot architecture:
*   **EEPROM Configuration:** Modified on each Pi 5 exactly once to try network boot, then NVMe, then SD using `BOOT_ORDER=0xf162`; `TFTP_PREFIX=0` uses each Pi's serial number for its TFTP directory.
*   **OS Mode:** Talos Linux (ARM64 architecture) loaded entirely into the Pi's system memory (RAM) via TFTP network streaming at boot time.
*   **Local Storage Mapping:** The high-speed combo NVMe drive is dedicated entirely to running local out-of-band Kubernetes system components (`/var/lib/containerd`, `/var/lib/kubelet`) and persisting RabbitMQ queue state data.

## 4. Isolated Network Topology
*   **Subnet Boundaries:** The cluster is isolated on its own network subnet (`192.168.45.0/24`).
*   **Gateway Host:** A Fedora 44 dual-homed host uses `enp112s0` (`a4:ae:11:1e:78:d4`, `192.168.1.251/24`) on the home LAN and `eno1` (altname `enp0s31f6`, `a4:ae:11:1e:78:d3`, `192.168.45.1/24`) on the cluster network. It provides DHCP, TFTP, Talos configuration HTTP, and a 2 TB NFS export bound to the cluster-side address. Local traffic is routed without masquerading on the gateway; the home router must permit cluster egress as needed.
*   **Home Router:** `192.168.1.1` has a static route for `192.168.45.0/24` via `192.168.1.251`.
*   **Ripping Host:** The separate ripping host is `192.168.1.32` and reaches the cluster through the home router.
*   **Address Plan:** Control plane `192.168.45.10`, workers `192.168.45.11` through `.16`, and dynamic DHCP leases `.50` through `.99`.

## 5. Workload, Data Tiering, & Quality Metrics
*   **Ingest Phase:** The ripping host uses `makemkvcon` to rip physical media losslessly to the gateway-hosted NFS export.
*   **Automation Queue:** A Python watchdog on the ripping host uses `ffprobe` to determine video dimensions, maps metadata, and ships tasks to RabbitMQ in the Talos cluster.
*   **Dynamic Autoscaling:** Monitored via KEDA to automatically spin up worker replicas up to a maximum of 7 when a job hits the queue, scaling completely down to 0 replicas during idle periods to preserve power.
*   **Transcoding Engine Parameters:** Compute worker containers execute headless `HandBrakeCLI` software transcoding streams using system RAM. CPU utilization limits are constrained to `3500m` (3.5 cores per node) to maintain system stability.
    *   **DVD Profiles:** Target `x264` codec, Constant Rate Factor (`-q 19`), default English tracking pass-through (`--audio-lang-list eng`), and active interlacing correction filters (`--comb-detect --yadif=default`).
    *   **Blu-ray Profiles:** Target `x265_10bit` codec, Constant Rate Factor (`-q 22`), medium encoding efficiency, and strict high-fidelity English audio track pass-through mirroring source bitstreams (`--aencoder copy`).

## 6. Observability & Alarm Infrastructure
*   **Metrics Engine:** Prometheus Server scraping a system-wide `node-exporter` DaemonSet to track physical node properties (CPU temps > 82°C tracking ceiling limits) and internal RabbitMQ metadata channels.
*   **Dashboard Layer:** Grafana Server running inside the cluster exposed via NodePort (`32300`) displaying customized dashboard layouts mapping operational temperatures, workloads, and NVMe data throughput tracking.
*   **Alert Routing Pipeline:** Prometheus Alertmanager tracking anomaly state limits and pushing event alerts to an integrated Apprise API wrapper service, formatting data to route notification alarms directly to a private **Slack** workspace channel interface.

## 7. Repository Workflow
*   **Commit Messages:** Use [Conventional Commits](https://www.conventionalcommits.org/) with the format `<type>(<optional scope>): <description>`, for example `docs(network): clarify gateway and boot configuration`.

