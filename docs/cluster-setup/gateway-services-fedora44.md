# Fedora 44 Gateway Services

This guide configures the gateway host at `192.168.1.251` / `192.168.45.1` to provide cluster DHCP, TFTP, Talos configuration HTTP, and NFS services. It is separate from the ripping host (`192.168.1.32`).

## Network contract

| Role | Interface | Address |
| --- | --- | --- |
| Home LAN | `enp112s0` (`a4:ae:11:1e:78:d4`) | `192.168.1.251/24` |
| Cluster LAN | `eno1` (altname `enp0s31f6`, `a4:ae:11:1e:78:d3`) | `192.168.45.1/24` |
| Home router | n/a | `192.168.1.1` |
| Cluster DHCP pool | n/a | `192.168.45.50-192.168.45.99` |
| Static cluster nodes | n/a | Control plane `.10`, workers `.11-.16` |

The home router must have a route for `192.168.45.0/24` via `192.168.1.251`. The gateway routes between interfaces without masquerading. The home router's egress/firewall policy must allow cluster traffic where internet access is required.

## Important: Pi/Talos boot assets

This guide configures the gateway services, but it does not invent a TFTP boot filename or Talos kernel command line. Raspberry Pi EEPROM network boot requests firmware files through TFTP using the device's serial-number directory when `TFTP_PREFIX=0`. Talos Image Factory's Raspberry Pi generic example currently produces a raw disk image; it does not define the complete Raspberry Pi EEPROM/TFTP file tree.

Before booting the Pis, select and test the Talos-on-Pi boot chain and place its actual boot artifacts under `/var/lib/tftpboot`. Capture TFTP requests on `eno1` or inspect the Pi bootloader output to verify the requested paths. Do not add a `dhcp-boot` filename until the chosen boot flow requires and identifies one. See the [Raspberry Pi network-boot documentation](https://www.raspberrypi.com/documentation/computers/remote-access.html#network-boot-your-raspberry-pi) and [Talos boot-assets documentation](https://docs.siderolabs.com/talos/platform-specific-installations/boot-assets).

The intended EEPROM order is network, NVMe, SD: `BOOT_ORDER=0xf162`. With `TFTP_PREFIX=0`, the serial-number directory is used as the TFTP prefix. See [Talos initial setup](talos-initial-setup.md) for `talosctl` installation and machine configuration.

## Install packages and prepare paths

Install the Fedora services:

```bash
sudo dnf install dnsmasq nginx nfs-utils firewalld policycoreutils-python-utils
sudo systemctl enable --now firewalld
```

Create the service directories. `/mnt/nas/media/videos` must be backed by the intended 2 TB filesystem before it is exported; an NFS export declaration does not create a quota or set capacity.

```bash
sudo install -d -m 0755 /var/lib/tftpboot
sudo install -d -o root -g nginx -m 0750 /srv/www/talos-configs
findmnt -T /mnt/nas/media/videos
```

Confirm the last command reports the intended 2 TB backing filesystem; do not create the export directory on the root filesystem as a substitute for mounting the data volume.

Copy the example configuration files linked below into their Fedora paths:

- [dnsmasq cluster config](examples/fedora44-gateway/dnsmasq-cluster.conf) to `/etc/dnsmasq.d/cluster.conf`. Confirm `/etc/dnsmasq.conf` includes `/etc/dnsmasq.d`.
- [Nginx Talos config site](examples/fedora44-gateway/nginx-talos-configs.conf) to `/etc/nginx/conf.d/talos-configs.conf`.
- [NFS export](examples/fedora44-gateway/cluster-media.exports) to `/etc/exports.d/cluster-media.exports`.
- [IP forwarding sysctl drop-in](examples/fedora44-gateway/90-cluster-gateway.conf) to `/etc/sysctl.d/90-cluster-gateway.conf`.

From the repository root, install the examples:

```bash
sudo install -D -m 0644 docs/cluster-setup/examples/fedora44-gateway/dnsmasq-cluster.conf /etc/dnsmasq.d/cluster.conf
sudo install -D -m 0644 docs/cluster-setup/examples/fedora44-gateway/nginx-talos-configs.conf /etc/nginx/conf.d/talos-configs.conf
sudo install -D -m 0644 docs/cluster-setup/examples/fedora44-gateway/cluster-media.exports /etc/exports.d/cluster-media.exports
sudo install -D -m 0644 docs/cluster-setup/examples/fedora44-gateway/90-cluster-gateway.conf /etc/sysctl.d/90-cluster-gateway.conf
```

If `/etc/dnsmasq.conf` does not include `/etc/dnsmasq.d`, add the Fedora `conf-dir` setting there; do not replace the whole packaged configuration with the example snippet.

## Serve Talos machine configurations

Place generated machine configurations in `/srv/www/talos-configs` with one file per node. For example, the control-plane URL is:

`http://192.168.45.1/talos-configs/controlplane.yaml`

Use distinct worker files such as `worker-01.yaml` through `worker-06.yaml`, and set each node's `talos.config=` kernel argument to its own URL. Restrict these files to the cluster subnet: machine configuration contains cluster credentials. The Nginx example binds only to `192.168.45.1`, denies other source subnets, and disables directory listings.

Apply an SELinux read-only web-content label and restrictive file permissions:

```bash
sudo semanage fcontext -a -t httpd_sys_content_t '/srv/www/talos-configs(/.*)?'
sudo restorecon -RFv /srv/www/talos-configs
sudo chown -R root:nginx /srv/www/talos-configs
sudo find /srv/www/talos-configs -type d -exec chmod 0750 {} +
sudo find /srv/www/talos-configs -type f -exec chmod 0640 {} +
```

Inspect the full Nginx configuration with `sudo nginx -T`. Disable or adjust any packaged default virtual host that listens on all addresses; this gateway should serve Talos configs only on `192.168.45.1`.

## Serve TFTP boot assets

The [dnsmasq example](examples/fedora44-gateway/dnsmasq-cluster.conf) listens only on `eno1` / `192.168.45.1`, leases `.50-.99`, and serves TFTP from `/var/lib/tftpboot`. It advertises the TFTP server address but intentionally omits a boot filename. The required boot filenames and per-serial directory layout depend on the selected Raspberry Pi/Talos boot chain; populate this tree only with verified artifacts.

Keep TFTP files and directories readable by the dnsmasq service, and label them with the Fedora TFTP SELinux type:

```bash
sudo semanage fcontext -a -t tftpdir_t '/var/lib/tftpboot(/.*)?'
sudo restorecon -RFv /var/lib/tftpboot
```

## Export the NFS share

The example exports `/mnt/nas/media/videos` as the NFSv4 pseudo-root (`fsid=0`) to `192.168.45.0/24`, read/write with `root_squash`. The NFSv4 client path for this export is `/`; keep the Kubernetes PV path consistent with that pseudo-root. Set filesystem ownership/ACLs for the worker process UIDs instead of disabling root squashing or making the directory world-writable.

Apply the SELinux context for a writable public NFS export, then load the export and enable the service:

```bash
sudo semanage fcontext -a -t public_content_rw_t '/mnt/nas/media/videos(/.*)?'
sudo restorecon -RFv /mnt/nas/media/videos
sudo setsebool -P nfsd_anon_write on
sudo exportfs -rav
sudo systemctl enable --now nfs-server
sudo exportfs -v
```

The sample PV's `2T` capacity is a Kubernetes scheduling declaration, not an NFS quota. Enforce the 2 TB limit on the backing filesystem or storage layer.

## Bind firewalld services and forwarding

Check current zone assignments before changing them:

```bash
sudo firewall-cmd --get-active-zones
```

Keep `enp112s0` in its current home-LAN zone. Create a dedicated `cluster` zone if it does not already exist, and assign only `eno1` to it. Allow DHCP, TFTP, HTTP, and NFS on that zone:

```bash
sudo firewall-cmd --permanent --new-zone=cluster
sudo firewall-cmd --permanent --zone=cluster --change-interface=eno1
sudo firewall-cmd --permanent --zone=cluster --add-service=dhcp
sudo firewall-cmd --permanent --zone=cluster --add-service=tftp
sudo firewall-cmd --permanent --zone=cluster --add-service=http
sudo firewall-cmd --permanent --zone=cluster --add-service=nfs
```

Run `--new-zone=cluster` only if the zone does not already exist. Determine the existing zone on `enp112s0`; do not move that interface into the new zone:

```bash
HOME_ZONE=$(sudo firewall-cmd --get-zone-of-interface=enp112s0)
printf 'Home interface zone: %s\n' "$HOME_ZONE"
```

Create stateful forwarding policies between the cluster and home zones. These examples allow the two routed subnets to communicate; only use them if the home zone is trusted. If that zone contains other networks, replace it with a dedicated home-LAN zone or narrow the policy before applying. Run `--new-policy` only when each policy does not already exist.

```bash
sudo firewall-cmd --permanent --new-policy=cluster-to-home
sudo firewall-cmd --permanent --policy=cluster-to-home --add-ingress-zone=cluster
sudo firewall-cmd --permanent --policy=cluster-to-home --add-egress-zone="$HOME_ZONE"
sudo firewall-cmd --permanent --policy=cluster-to-home --set-target=ACCEPT

sudo firewall-cmd --permanent --new-policy=home-to-cluster
sudo firewall-cmd --permanent --policy=home-to-cluster --add-ingress-zone="$HOME_ZONE"
sudo firewall-cmd --permanent --policy=home-to-cluster --add-egress-zone=cluster
sudo firewall-cmd --permanent --policy=home-to-cluster --set-target=ACCEPT
```

Do not add a masquerade rule for the cluster subnet on this gateway. The home router handles internet egress according to its own policy.

## Start and verify services

Validate the service configurations, load the sysctl drop-in, reload firewalld, then start the services:

```bash
sudo sysctl --system
sudo dnsmasq --test
sudo nginx -t
sudo exportfs -rav
sudo firewall-cmd --reload
sudo systemctl enable --now dnsmasq nginx nfs-server
```

From a host on the cluster network, verify a Talos configuration URL:

```bash
curl --fail --show-error http://192.168.45.1/talos-configs/controlplane.yaml -o /dev/null
```

Watch DHCP/TFTP activity while booting one Pi:

```bash
sudo journalctl -fu dnsmasq
sudo tcpdump -ni eno1 'port 67 or port 69'
```

Verify the NFS export from a cluster client by mounting `192.168.45.1:/` with NFSv4.1. Do not proceed to fleet rollout until the Pi's actual TFTP request paths and Talos configuration URL have both been verified.
