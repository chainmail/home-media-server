# Home Media Server

Documentation and host files for home media ingestion and Raspberry Pi transcoding. The guides cover cluster architecture, Talos provisioning, networking, storage, RabbitMQ, transcoding profiles, ingest automation, and local Podman testing.

The earlier project description mentioned Jellyfin, but the current guides do not document its installation or configuration.

## Recommended Reading Order

This is a suggested route through the existing material, not confirmation that every example is consistent or production-ready. The consolidated architecture manual repeats material from the focused guides.

1. [Cluster blueprint](docs/architecture/cluster-blueprint.md) for the architecture and hardware overview.
2. [System schematic](docs/architecture/diagram1-schematic.md) for component and network relationships.
3. [Routing setup](docs/cluster-setup/routing-setup.md) for gateway and cluster network preparation.
4. [Fedora 44 gateway services](docs/cluster-setup/gateway-services-fedora44.md) for DHCP, TFTP, Nginx, NFS, firewalld, and `talosctl` setup.
5. [Talos initial setup](docs/cluster-setup/talos-initial-setup.md) for machine configuration and bootstrap.
6. [Cluster manifest](docs/cluster-setup/cluster-manifest.md) for provisioning and Kubernetes examples.
7. [NFS persistent storage](docs/services/nfs-persistent.md) and [RabbitMQ setup](docs/services/rabbitmq-setup.md) for workload dependencies.
8. [HandBrake settings](docs/media-processing/handbrake-settings.md) for encoding profiles.
9. [Ingest daemon](scripts/update-ingest-daemon.py) for file watching and profile selection.
10. [Stateless transcoding manual](docs/architecture/stateless-transcode-cluster.md) as a cross-topic reference.

For local testing, read [Podman network](docs/testing/podman-network.md) before [Podman watchdog integration](docs/testing/podman-python-watchdog.md).

## Contents

- Architecture
  - [Cluster blueprint](docs/architecture/cluster-blueprint.md)
  - [System schematic](docs/architecture/diagram1-schematic.md)
  - [Stateless transcoding manual](docs/architecture/stateless-transcode-cluster.md)
- Cluster setup
  - [Routing setup](docs/cluster-setup/routing-setup.md)
  - [Fedora 44 gateway services](docs/cluster-setup/gateway-services-fedora44.md)
  - [Talos initial setup](docs/cluster-setup/talos-initial-setup.md)
  - [Cluster manifest](docs/cluster-setup/cluster-manifest.md)
- Services and processing
  - [NFS persistent storage](docs/services/nfs-persistent.md)
  - [RabbitMQ setup](docs/services/rabbitmq-setup.md)
  - [HandBrake settings](docs/media-processing/handbrake-settings.md)
  - [Ingest daemon](scripts/update-ingest-daemon.py)
- Local testing
  - [Podman network](docs/testing/podman-network.md)
  - [Podman watchdog integration](docs/testing/podman-python-watchdog.md)

## Repository Layout

```text
home-media-server/
├── AGENTS.md
├── README.md
├── LICENSE
├── docs/
│   ├── architecture/
│   │   ├── cluster-blueprint.md
│   │   ├── diagram1-schematic.md
│   │   └── stateless-transcode-cluster.md
│   ├── cluster-setup/
│   │   ├── cluster-manifest.md
│   │   ├── gateway-services-fedora44.md
│   │   ├── examples/
│   │   │   └── fedora44-gateway/
│   │   │       ├── 90-cluster-gateway.conf
│   │   │       ├── cluster-media.exports
│   │   │       ├── dnsmasq-cluster.conf
│   │   │       └── nginx-talos-configs.conf
│   │   ├── routing-setup.md
│   │   └── talos-initial-setup.md
│   ├── media-processing/
│   │   └── handbrake-settings.md
│   ├── services/
│   │   ├── nfs-persistent.md
│   │   └── rabbitmq-setup.md
│   └── testing/
│       ├── podman-network.md
│       └── podman-python-watchdog.md
├── scripts/
│   └── update-ingest-daemon.py
└── root/usr/
    ├── bin/beets-processing.py
    └── lib/systemd/system/
        ├── beets-automation.service
        └── beets-automation.timer
```

## Documentation Notes

- Network source of truth: ripping host `192.168.1.32`; gateway `enp112s0` at `192.168.1.251/24` and `eno1` (altname `enp0s31f6`) at `192.168.45.1/24`; home router `192.168.1.1` routes `192.168.45.0/24` via `192.168.1.251`. DHCP uses `.45.50-.99`; nodes use static `.45.10-.16`.
- The Fedora 44 gateway serves a 2 TB NFS export to `192.168.45.0/24`. The Talos templates use `eth0`; verify that name against each Pi's Talos interface inventory.
- Pi boot order is network, NVMe, then SD (`BOOT_ORDER=0xf162`).
- Nginx serves per-node Talos configs from `http://192.168.45.1/talos-configs/<node-config>.yaml`. TFTP boot artifacts still need to be generated and verified for the selected Pi/Talos boot chain.
- The observability sample in the system schematic is marked as an unvalidated draft; confirm its API versions and operators before applying it.
- The project files include a `root/usr` tree for host-level service files; that deployment layout remains separate from the documentation hierarchy.
