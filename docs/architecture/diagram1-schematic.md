This manual provides a detailed network schematic and operational architecture for your stateless, distributed transcoding cluster. It includes metrics collection via Prometheus, dashboard visualization via Grafana, and central notification routing using [Apprise](https://github.com/caronc/apprise). [1] 
## 1. Architecture and Routing Schematic

The home router (`192.168.1.1`) routes `192.168.45.0/24` through the gateway host at `192.168.1.251`.

```text
====================================================================================================
                                      PRIMARY LAN: 192.168.1.0/24
====================================================================================================
                                                 │
                                    ┌─────────────────────────────┐     ┌──────────────────────────────────────────────┐
                                    │ RIPPING / INGEST HOST       │     │ GATEWAY HOST                                 │
                                    │ 192.168.1.32                │     │ LAN: 192.168.1.251                           │
                                    │ Optical drives and watchdog │     │ Cluster: 192.168.45.1                       │
                                    │ RabbitMQ producer           │     │ Routing, DHCP, TFTP, Talos HTTP, and NFS    │
                                    └─────────────────────────────┘     └───────────────────────┬──────────────────────┘
                                                        │
                                            ┌──────────────────────────────────────────────┘
                                            ▼ [Cluster interface: 192.168.45.1; routed, no NAT]
====================================================================================================
                                    ISOLATED CLUSTER SUBNET: 192.168.45.0/24
====================================================================================================
         │                                       │                                  │
         ▼ [PXE Netboot Request]                 ▼ [Mount NFS Streams]              ▼ [AMQP Msg]
 ┌───────────────────────────────┐       ┌──────────────────────────────┐   ┌──────────────────────┐
 │ GATEWAY SERVICES              │       │ GATEWAY NFS EXPORT           │   │ K8s MANAGED SWITCH   │
 │                               │       │                              │   │                      │
 │ - DHCP Server (dnsmasq)       │       │ - Export Path:               │   │ - IEEE 802.3at (PoE+)│
 │ - TFTP Boot Stream Handler    │       │   /mnt/nas/media/videos      │   │ - 150W Power Budget  │
 │ - Talos config HTTP           │       │ - Protocol: NFSv4             │   │ - Uplinks 7x Pi Nodes│
 └───────────────────────────────┘       └──────────────────────────────┘   └──────────┬───────────┘
                                                                                       │
 ┌─────────────────────────────────────────────────────────────────────────────────────┘
 │
 ▼ [Cluster Ethernet Fabric]
 ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ TALOS LINUX KUBERNETES INFRASTRUCTURE (Fleet Subnet Space)                                      │
 │                                                                                                 │
 │  ┌───────────────────────────────────────────────────────────────────────────────────────────┐  │
 │  │ CONTROL PLANE NODE: k8s-master-01 (192.168.45.10) [In-Memory OS Cache]                    │  │
 │  │ └── Combo NVMe: Partitioned for Container Storage Engine Caching & Kubelet Scratchpads    │  │
 │  └───────────────────────────────────────────────────────────────────────────────────────────┘  │
 │                                                                                                 │
 │  ┌───────────────────────────────────────────────────────────────────────────────────────────┐  │
 │  │ COMPUTE WORKER NODES: k8s-worker-01 through k8s-worker-06 (192.168.45.11 - .16)           │  │
 │  │                                                                                           │  │
 │  │  ┌─────────────────────────────────────────────────────────────────────────────────────┐  │  │
 │  │  │ Headless Processing Worker Pods (davidmatthews/handbrake-cli:latest)                │  │  │
 │  │  │ └── Thread Limits: Restricted to 3500m (3.5 Cores) to prevent hardware node freeze │  │  │
 │  │  └─────────────────────────────────────────────────────────────────────────────────────┘  │  │
 │  │  ┌─────────────────────────────────────────────────────────────────────────────────────┐  │  │
 │  │  │ Observability Exporters (Prometheus Node Exporter DaemonSet)                        │  │  │
 │  │  │ └── Metric Telemetry: Tracks thermal metrics and NVMe storage I/O limits            │  │  │
 │  │  └─────────────────────────────────────────────────────────────────────────────────────┘  │  │
 │  └───────────────────────────────────────────────────────────────────────────────────────────┘  │
 │                                                                                                 │
 │  ┌───────────────────────────────────────────────────────────────────────────────────────────┐  │
 │  │ CORE APP ENGINE NAMESPACE: rabbitmq-system                                                │  │
 │  │                                                                                           │  │
 │  │  ┌─────────────────────────────┐   ┌─────────────────────────────┐   ┌──────────────────┐ │  │
 │  │  │ Containerized RabbitMQ      │   │ KEDA Autoscaler Engine      │   │ Apprise API      │ │  │
 │  │  │                             │   │                             │   │ Notification Pod │ │  │
 │  │  │ - Service Port: 5672 (AMQP) │   │ - Polling Interval: 15s     │   │                  │ │  │
 │  │  │ - UI NodePort: 31672        │   │ - Metric Hook: Queue Length │   │ - Target:        │ │  │
 │  │  │ - State: NVMe local-path    │   │ - Target: Scale 0 to 7 Pods │   │   Discord/Slack  │ │  │
 │  │  └─────────────────────────────┘   └─────────────────────────────┘   └──────────────────┘ │  │
 │  │                                                                                           │  │
 │  │  ┌──────────────────────────────────────────────┐   ┌──────────────────────────────────┐  │  │
 │  │  │ Prometheus Core Server                       │   │ Grafana Metrics Visualization    │  │  │
 │  │  │                                              │   │                                  │  │  │
 │  │  │ - Scrapes Worker Node Exporters every 10s    │──>│ - Exposes Dashboards             │  │  │
 │  │  │ - Evaluates Cluster AlertManager Rules       │   │ - Endpoint Route: NodePort 32300 │  │  │
 │  │  └──────────────────────────────────────────────┘   └──────────────────────────────────┘  │  │
 │  └───────────────────────────────────────────────────────────────────────────────────────────┘  │
 └─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 2. Metrics Collection and Alerting

To track cluster health, the monitoring ecosystem captures physical system metrics (temperatures and compute load) alongside state telemetry from the transcoding queue.

### 2.1 Metric Telemetry Collection Flow

1. **Node metrics:** A `node-exporter` DaemonSet reads host metrics, including thermal data.
2. **Collection:** Prometheus scrapes node exporters and RabbitMQ metrics.
3. **Alert evaluation:** Prometheus evaluates configured alert rules.
4. **Notification:** Alertmanager sends alerts to the [Apprise API](https://github.com/caronc/apprise-api), which routes them to configured notification services.

## 3. Observability Manifests

Deploy these infrastructure manifests to enable metrics collection, dashboard visualization, and notification routing inside your cluster.
Save the manifest as `cluster-monitoring.yaml` and apply it using:

```bash
kubectl apply -f cluster-monitoring.yaml
```

The following draft is not a validated Kubernetes manifest; several API version fields and line breaks are incomplete. Confirm the intended operators and API versions before applying it.

```text
apiVersion: apps/v1kind: Deploymentmetadata:
  name: apprise-notification-engine
  namespace: rabbitmq-system
  labels:
    app: apprise-gatespec:
  replicas: 1
  selector:
    matchLabels:
      app: apprise-gate
  template:
    metadata:
      labels:
        app: apprise-gate
    spec:
      containers:
      - name: apprise
        image: caronc/apprise:latest # Official stable notification abstraction microservice
        ports:
        - containerPort: 8000
---apiVersion: v1kind: Servicemetadata:
  name: apprise-service
  namespace: rabbitmq-systemspec:
  ports:
  - port: 8000
    targetPort: 8000
  selector:
    app: apprise-gate
---apiVersion: ://coreos.comkind: PrometheusRulemetadata:
  name: cluster-hardware-alarms
  namespace: rabbitmq-systemspec:
  groups:
  - name: hardware.rules
    rules:
    - alert: RaspberryPiThermalThrottlingRisk
      expr: node_thermal_zone_temp{type="cpu-thermal"} > 82
      for: 2m
      labels:
        severity: critical
      annotations:
        summary: "Node {{ $labels.instance }} thermal threshold exceeded"
        description: "Raspberry Pi 5 CPU core temperature is at {{ $value }}°C. Active cooler failure or environment air-saturation suspected."
    - alert: TranscodeQueueBacklogSpike
      expr: rabbitmq_queue_messages{queue="transcode_jobs"} > 30
      for: 10m
      labels:
        severity: warning
      annotations:
        summary: "Transcode execution queue build up"
        description: "RabbitMQ message depth has exceeded 30 items for 10 minutes. Compute nodes may be stalling under load."
---apiVersion: ://coreos.comalpha1kind: AlertmanagerConfigmetadata:
  name: apprise-alert-routing
  namespace: rabbitmq-systemspec:
  route:
    groupBy: ['alertname']
    groupWait: 30s
    groupInterval: 5m
    repeatInterval: 3h
    receiver: 'apprise-webhook'
  receivers:
  - name: 'apprise-webhook'
    webhookConfigs:
    - url: 'http://cluster.local' # Replace with your destination apprise tokens
  ```

  ## 4. System Lifecycle Monitoring Checklist

   - **Grafana:** Access the configured dashboard at `http://192.168.45.10:32300`.
   - **Apprise:** Configure notification destinations in the Apprise service.

[1] [https://github.com](https://github.com/caronc/apprise/blob/master/README.md)
[2] [https://appriseit.com](https://appriseit.com/api/integrations/)
[3] [https://www.home-assistant.io](https://www.home-assistant.io/integrations/apprise/)

