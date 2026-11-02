# From zero to serving a model on Kubernetes, on your own machine

[![contribute to this guide](https://img.shields.io/badge/contribute-to%20this%20guide-2ea44f?logo=github)](https://github.com/AlexsJones/axjns-k8s-local-llm)

*The article I wish I'd had a year or two ago.*

If you ran Kubernetes for a living a few years back and you're coming back to it because of AI, welcome back. Most of what you knew still holds. Pods, Deployments, Services, PVCs: all the same. What's new is the bit in the middle: getting a model onto the box, getting a GPU into a pod, and knowing what's actually going on when it breaks.

Every "run an LLM on Kubernetes" tutorial I found either used a toy model on CPU or assumed a cloud account with a rack of H100s. This one runs on the laptop or desktop you already have. Everything below was run for real, and the output you see is what came back.

### Full disclosure: some of these tools are mine

This guide leans on a couple of projects I've built, because they're what I actually reach for when I set this up:

- **[llmfit](https://github.com/AlexsJones/llmfit)** works out which model will fit your hardware before you download anything. That's step 1.
- **[k8sgpt](https://github.com/k8sgpt-ai/k8sgpt)** is a CNCF Sandbox project that I created and still maintain. It's the payoff at the end: it uses the model you've just served to diagnose problems in your own cluster.

The Kubernetes parts are all stock kind, kubectl and Ollama, so if you'd rather use something else for either job, swap it in.

### What your machine needs

Everything runs in one kind node, and that node is a container on your machine, so the node's capacity is your laptop or desktop's. On every path, the model server asks Kubernetes for the same things:

| Pod asks for | Amount |
|---|---|
| CPU | requests 4 cores, no limit |
| Memory | requests 4 GiB, limited to 8 GiB |
| Accelerator | nothing on CPU; one `gpu.intel.com/xe`, `nvidia.com/gpu` or `amd.com/gpu` on the GPU paths |
| Model volume | a 20 Gi PVC (kind's local-path storage doesn't enforce the size; the model takes 1.9 GB) |

And the accelerator and host setup each path needs:

| Path | Accelerator | Host side |
|---|---|---|
| CPU only | none | nothing extra |
| Intel Arc | Intel Arc / Xe graphics, integrated or discrete | `xe` kernel driver and `/dev/dri`. Older GPUs on `i915` advertise `gpu.intel.com/i915`, so change the resource name in the manifest |
| NVIDIA | a GPU with CUDA compute capability 5.0 or newer ([Ollama's GPU list](https://docs.ollama.com/gpu)) | NVIDIA driver 550 or newer (`nvidia-smi` works) and the NVIDIA Container Toolkit configured for Docker |
| AMD | a Radeon or Instinct GPU on [Ollama's ROCm list](https://docs.ollama.com/gpu) | `amdgpu` kernel driver, with `/dev/kfd` and `/dev/dri` present |

- **CPU and RAM.** The node needs 4 free cores and 4 GiB to schedule the pod, which can then grow to 8 GiB. As a rule of thumb, 8 cores and 16 GB of RAM leaves room for your OS, Docker and the kind control plane as well; extra cores mainly speed up the CPU path. Both machines I tested on had plenty: the Framework 13 has 16 cores and 62 GB, and the Framework desktop has 32 threads and 62 GB of system RAM, with another 64 GB set aside for the GPU.
- **GPU memory.** Integrated GPUs and APUs (the Arc B390, the Radeon 8060S) use system memory, and Ollama sees the GPU's pool rather than the pod's 8 GiB limit: 46.7 GiB on the laptop, 64 GiB on the desktop. `llama3.2:3b` used 1.9 GB of weights plus its KV cache, 3.1 GB in total on AMD with an 8192-token context. On a discrete card, 4 GB of VRAM should be enough for this model at that context (a rule of thumb, not something I measured on NVIDIA).
- **Disk.** Measured after my runs: the kind node image is 1.34 GB, the node's own image store grew to 5.8 GB with `ollama/ollama:0.40.13` (Intel laptop) and 4.1 GB with `ollama/ollama:0.40.13-rocm` (AMD desktop), and the model is 1.9 GB. Budget about 10 GB free. The downloads are 3.39 GB for `ollama/ollama:0.40.13` (the CPU, Intel and NVIDIA image; it bundles CUDA), 1.45 GB for the `-rocm` image, 0.39 GB for `kindest/node:v1.37.0` and 2.02 GB for the model.
- **OS and container runtime.** Linux with Docker; I used Docker 29.7.2 on Fedora 43 and 44. kind also supports Podman. The GPU paths pass `/dev/dri` (and `/dev/kfd` for AMD) from the host into the node, so they need a Linux host.
- **Bigger models.** All of the above is sized for a 3B model. For anything bigger, ask llmfit (step 1) what fits your pod's limits, then raise the memory limit and disk to match.

> **Pick your hardware once** and every hardware-specific step on this page switches to match. On GitHub you'll just see all four versions one after another.

**Tested on:** Framework 13 (Intel Core Ultra X7 358H, 16 cores, 62 GB RAM, Intel Arc B390), Fedora 44, kernel 7.1.13, Docker 29.7.2, kind v0.33.0, Kubernetes v1.37.0 (`kindest/node:v1.37.0`), Ollama 0.40.13, model `llama3.2:3b` (Q4_K_M). The AMD path was run on a Framework desktop (Ryzen AI Max+ 395, Radeon 8060S, gfx1151), Fedora 43, kernel 7.1.8, same kind, node image and Ollama versions.

**Versions verified on 2 November 2026.** See the [version table](#versions) at the end.

<!-- picker -->

---

## What you need

- **Docker** (or Podman). kind runs each Kubernetes node as a container.
- **kind v0.33.0**, **kubectl v1.37.x** and **helm**. kubectl only supports one minor version either side of the server, so an older 1.35 kubectl will misbehave against these 1.37 clusters; `kubectl version` should show a 1.36, 1.37 or 1.38 client. kind v0.33.0 is the newest release, and `kindest/node:v1.37.0` is the newest kind node image as of November 2026 (upstream Kubernetes is at 1.37.2; kind hasn't published a newer image yet).
- **[llmfit](https://github.com/AlexsJones/llmfit) v1.1.18**, to pick a model that will actually fit your hardware. (Yes, I wrote it.)
- **[k8sgpt](https://github.com/k8sgpt-ai/k8sgpt)**, for the last step, when your model debugs your cluster. (I created and maintain that one too.)
- **k9s**, optional, but it's the nicest way to watch a cluster.
- About **10 GB of free disk** and a decent connection (see [what your machine needs](#what-your-machine-needs) for the breakdown).

I keep everything in one directory, binaries included, so nothing touches my main kubeconfig or system:

```bash
mkdir -p ~/Code/axjns-k8s-local-llm/bin && cd ~/Code/axjns-k8s-local-llm
curl -sSLo bin/kind https://kind.sigs.k8s.io/dl/v0.33.0/kind-linux-amd64 && chmod +x bin/kind
export PATH=$PWD/bin:$PATH
curl -sSLo bin/kubectl https://dl.k8s.io/release/v1.37.2/bin/linux/amd64/kubectl && chmod +x bin/kubectl
curl -sSL https://github.com/AlexsJones/llmfit/releases/download/v1.1.18/llmfit-v1.1.18-x86_64-unknown-linux-gnu.tar.gz | tar -xz -C bin --strip-components=1 llmfit-v1.1.18-x86_64-unknown-linux-gnu/llmfit
export PATH=$PWD/bin:$PATH
export KUBECONFIG=$PWD/kubeconfig   # this cluster gets its own kubeconfig file
kind version && kubectl version --client && llmfit --version
```

```text
kind v0.33.0 go1.26.7 linux/amd64
Client Version: v1.37.2
Kustomize Version: v5.8.1
llmfit 1.1.18
```

On a Mac or with Homebrew, `brew install kind kubectl helm k9s llmfit k8sgpt` gets you most of the way. Check `kind version` says v0.33.0.

---

## Step 1: pick a model with llmfit

This is the step people skip, and it's the one that decides whether the rest of the afternoon goes well. The most common way to waste a day with local models is to download one that doesn't fit: it either won't load, or it spills out of GPU memory onto the CPU and crawls. **[llmfit](https://github.com/AlexsJones/llmfit) is how you pick the right model for your hardware before you download anything.** It detects your CPU, RAM, memory bandwidth and GPU, then scores thousands of models on whether they fit, how fast they'll run, and which quantisation to use.

Start by asking it what it sees:

```bash
llmfit system
```

<!-- tab:cpu intel nvidia -->
On my Framework 13 laptop it finds the Arc B390 and the shared memory:

![llmfit system on the Framework 13 laptop: Intel Core Ultra X7 358H, 62 GB RAM, Intel Arc B390](img/term-llmfit-system-intel.png)
<!-- /tab -->

<!-- tab:amd -->
On my Framework desktop it finds the Radeon 8060S and picks the ROCm backend:

![llmfit system on the Framework desktop: Ryzen AI Max+ 395, Radeon 8060S, ROCm backend](img/term-llmfit-system-amd.png)
<!-- /tab -->

Then ask for a shortlist. `llmfit fit` ranks every model it knows against your machine; I've filtered it to the big model families so the list is readable:

```bash
llmfit fit -n 8 --providers meta,google,alibaba --sort score
```

<!-- tab:cpu intel nvidia -->
![llmfit fit on the Intel laptop: a ranked table of models with fit status, estimated tok/s, quantisation and memory use](img/term-llmfit-fit-intel.png)
<!-- /tab -->

<!-- tab:amd -->
![llmfit fit on the AMD desktop: a ranked table of models with fit status, estimated tok/s, quantisation and memory use](img/term-llmfit-fit-amd.png)
<!-- /tab -->

Same command, two machines, two different answers. That's the point: the right model depends on the box. Run `llmfit` with no arguments for the interactive version, where you can search, filter and sort.

Here's the trick that matters for Kubernetes: **the model doesn't get your whole machine, it gets whatever the pod's limits say.** So ask llmfit about the pod, not the laptop. I'm going to give the model server 4 CPUs and an 8 GiB memory limit, and check a small Llama:

```bash
llmfit --ram 8G --cpu-cores 4 info meta-llama/Llama-3.2-3B-Instruct
```

![llmfit info for Llama 3.2 3B constrained to 8 GB and 4 cores: Perfect fit, memory requirements per quantisation](img/term-llmfit-info-intel.png)

The lines that matter are at the bottom: at Q4_K_M it needs about 2 GB, it's a 🟢 Perfect fit in 8 GiB, and llmfit gives a baseline speed estimate you can check later against the real number. A 3B model is small, but it's good enough to hold a conversation and it runs on everything on this page, so that's what we'll use. Ollama calls it `llama3.2:3b`. `llmfit --ram 8G --cpu-cores 4 recommend --use-case chat` gives you a shortlist if you want something else.

> **Going further:** [llmfit-dra](https://github.com/sympozium-ai/llmfit-dra) takes the same fit maths into the cluster as a Dynamic Resource Allocation driver. You ask for a model and a minimum tok/s, and the stock scheduler places the pod on a device that can actually deliver it. Overkill for one node, but it's where this is heading.

Why Ollama and not vLLM? For one box with no datacenter GPU, Ollama is the one that just works: one image, CPU and GPU backends included, an OpenAI-compatible API, and it pulls models by name. vLLM is what you'd reach for on real NVIDIA hardware with many concurrent users; its CPU build exists but is a lot more fiddly for a first run.

---

## Step 2: create the cluster

One node is plenty. The node image is pinned by digest so you get exactly what I tested.

<!-- tab:cpu intel -->
`kind-local-llm.yaml`:

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: local-llm
nodes:
  - role: control-plane
    # newest kind node image as of Nov 2026 (kind v0.33.0). Upstream is at 1.37.2.
    image: kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5
    extraMounts:
      - hostPath: /dev/dri
        containerPath: /dev/dri
```

The `/dev/dri` mount is only needed for the Intel GPU step. It's harmless on CPU (kind nodes are privileged containers, so the node can see it anyway; this just makes it explicit).

```bash
kind create cluster --config kind-local-llm.yaml --kubeconfig ./kubeconfig
kubectl get nodes -o wide
```

```text
Creating cluster "local-llm" ...
 ✓ Ensuring node image (kindest/node:v1.37.0) 🖼️
 ✓ Preparing nodes 📦
 ✓ Writing configuration 📜
 ✓ Starting control-plane 🕹️
 ✓ Installing CNI 🔌
 ✓ Installing StorageClass 💾
Set kubectl context to "kind-local-llm"
...
NAME                      STATUS     ROLES           AGE   VERSION   ...   OS-IMAGE                       KERNEL-VERSION                   CONTAINER-RUNTIME
local-llm-control-plane   NotReady   control-plane   5s    v1.37.0   ...   Debian GNU/Linux 13 (trixie)   7.1.13-200.fc44.x86_64 (amd64)   containerd://2.3.4
```

It goes `Ready` a few seconds later. My first run took 141 seconds because it was downloading the ~1 GB node image; with the image cached it's 10 to 20 seconds.

![kind create cluster on the laptop, then kubectl get nodes showing v1.37.0](img/term-kind-create-intel.png)
<!-- /tab -->

<!-- tab:nvidia -->
This follows NVIDIA's own [nvkind](https://github.com/NVIDIA/nvkind) docs.

GPUs in kind are awkward with NVIDIA because the node is itself a container, so the NVIDIA runtime has to inject the GPU into the node, and then the node's containerd needs the toolkit too. NVIDIA wrote `nvkind` to do all of that. You need a working driver (`nvidia-smi -L` works) and the NVIDIA Container Toolkit installed for Docker. Then, once, on the host:

```bash
sudo nvidia-ctk runtime configure --runtime=docker --set-as-default --cdi.enabled
sudo nvidia-ctk config --set accept-nvidia-visible-devices-as-volume-mounts=true --in-place
sudo systemctl restart docker
```

Then either use nvkind (recommended):

```bash
go install github.com/NVIDIA/nvkind/cmd/nvkind@latest
nvkind cluster create --name local-llm --image kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5
```

or plain kind with the volume-mount trick that nvkind uses under the hood, `kind-local-llm-nvidia.yaml`:

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: local-llm
nodes:
  - role: control-plane
    # newest kind node image as of Nov 2026 (kind v0.33.0). Upstream is at 1.37.2.
    image: kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5
    extraMounts:
      - hostPath: /dev/null
        containerPath: /var/run/nvidia-container-devices/all
```

```bash
kind create cluster --config kind-local-llm-nvidia.yaml --kubeconfig ./kubeconfig
```

With plain kind you still need the toolkit inside the node, which is the part nvkind automates. That's why I'd use nvkind.
<!-- /tab -->

<!-- tab:amd -->
> **Tested** on a Framework desktop: Ryzen AI Max+ 395 with Radeon 8060S graphics (gfx1151), Fedora 43, kind v0.33.0, Kubernetes v1.37.0.

ROCm needs two device paths inside the node: the DRM render nodes (`/dev/dri`) and the ROCm compute interface (`/dev/kfd`). `kind-local-llm-amd.yaml`:

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: local-llm
nodes:
  - role: control-plane
    # newest kind node image as of Nov 2026 (kind v0.33.0). Upstream is at 1.37.2.
    image: kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5
    extraMounts:
      - hostPath: /dev/dri
        containerPath: /dev/dri
      - hostPath: /dev/kfd
        containerPath: /dev/kfd
```

Check the host first: `ls -l /dev/kfd /dev/dri` should show both, and `rocminfo` tells you your GPU's gfx target. On Fedora both `rocminfo` and `rocm-smi` come from the distro's `rocminfo` and `rocm-smi` packages; you only need them on the host for this check, the ROCm runtime itself ships inside the Ollama image.

![rocminfo and rocm-smi on the desktop: Radeon 8060S, gfx1151, 64 GiB VRAM](img/term-gpu-amd-host.png)

(`rocm-smi` also prints a harmless `libdrm_amdgpu.so` warning on Fedora 43, which I've left out of the screenshot.) Then:

```bash
kind create cluster --config kind-local-llm-amd.yaml --kubeconfig ./kubeconfig
kubectl get nodes -o wide
```

![kind create cluster on the AMD desktop in 10 seconds, kubectl get nodes showing v1.37.0](img/term-kind-create-amd.png)

10 seconds, because the node image was already cached.
<!-- /tab -->

---

## Step 3: serve the model

The whole thing is one Deployment, one PVC and one Service. The bit worth explaining is the init container: it starts Ollama, pulls the model into the PVC, and exits. The real container then starts with the model already on disk, and because it's a PVC, restarts don't download 2 GB again.

<!-- tab:cpu -->
`manifests/cpu/10-ollama.yaml` (the namespace is in `00-namespace.yaml`):

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ollama-models
  namespace: llm
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 20Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama
  namespace: llm
  labels:
    app: ollama
spec:
  replicas: 1
  strategy:
    type: Recreate          # RWO volume, so don't run two at once
  selector:
    matchLabels:
      app: ollama
  template:
    metadata:
      labels:
        app: ollama
    spec:
      initContainers:
        - name: pull-model
          image: ollama/ollama:0.40.13
          command: ["/bin/sh", "-c"]
          args:
            - |
              ollama serve >/tmp/serve.log 2>&1 &
              until ollama list >/dev/null 2>&1; do sleep 1; done
              ollama pull "$MODEL"
          env:
            - name: MODEL
              value: llama3.2:3b
          volumeMounts:
            - name: models
              mountPath: /root/.ollama
      containers:
        - name: ollama
          image: ollama/ollama:0.40.13
          ports:
            - name: http
              containerPort: 11434
          env:
            - name: OLLAMA_KEEP_ALIVE
              value: "24h"          # keep the model in memory between requests
            - name: OLLAMA_NUM_PARALLEL
              value: "1"
          resources:
            requests:
              cpu: "4"
              memory: 4Gi
            limits:
              memory: 8Gi
          readinessProbe:
            httpGet:
              path: /api/tags
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 30
            periodSeconds: 20
          volumeMounts:
            - name: models
              mountPath: /root/.ollama
      volumes:
        - name: models
          persistentVolumeClaim:
            claimName: ollama-models
---
apiVersion: v1
kind: Service
metadata:
  name: ollama
  namespace: llm
spec:
  selector:
    app: ollama
  ports:
    - name: http
      port: 80
      targetPort: http
```

Notice there's a memory limit but no CPU limit. CPU limits on inference mostly just throttle you; the request is enough to tell the scheduler what you need.

```bash
kubectl apply -f manifests/cpu/
```

```text
namespace/llm created
persistentvolumeclaim/ollama-models created
deployment.apps/ollama created
service/ollama created
```
<!-- /tab -->

<!-- tab:intel -->
Intel GPUs reach pods through Intel's GPU device plugin. It finds the GPU on the node and advertises it as a resource the scheduler understands. The Arc B390 uses the newer `xe` kernel driver, so the resource is `gpu.intel.com/xe` (older Intel GPUs on `i915` get `gpu.intel.com/i915`). No node labels or NFD needed for the base install:

```bash
kubectl apply -k 'https://github.com/intel/intel-device-plugins-for-kubernetes/deployments/gpu_plugin?ref=v0.37.1'
kubectl get node local-llm-control-plane -o jsonpath="{.status.allocatable}"
```

```text
daemonset.apps/intel-gpu-plugin created
{"cpu":"16","ephemeral-storage":"1997604388864","gpu.intel.com/xe":"1","hugepages-1Gi":"0","hugepages-2Mi":"0","memory":"65296284Ki","pods":"110"}
```

`gpu.intel.com/xe: 1`. The cluster can see the GPU.

![The Intel GPU plugin installed, the node advertising gpu.intel.com/xe, and Ollama's log line showing the Vulkan backend on the Arc GPU](img/term-gpu-intel-plugin.png)

For the model server, Ollama's Vulkan backend is the simplest route on Intel: it's in the normal `ollama/ollama` image, no oneAPI or SYCL image needed. The manifest is the CPU one with two changes, `manifests/intel/10-ollama-vulkan.yaml`:

```yaml
          env:
            - name: OLLAMA_KEEP_ALIVE
              value: "24h"
            - name: OLLAMA_NUM_PARALLEL
              value: "1"
            - name: OLLAMA_IGPU_ENABLE
              value: "1"            # Ollama skips integrated GPUs by default; the Arc B390 is one
          resources:
            requests:
              cpu: "4"
              memory: 4Gi
            limits:
              memory: 8Gi
              gpu.intel.com/xe: 1
```

The `OLLAMA_IGPU_ENABLE` line cost me a redeploy. Without it, Ollama finds the GPU and then ignores it:

```text
time=2026-11-02T11:51:09.106Z level=INFO source=runner.go:405 msg="dropping integrated GPU; to enable, set OLLAMA_IGPU_ENABLE=1" id=0 library=Vulkan compute=0.0 name=Vulkan0 description="Intel(R) Graphics (PTL)" pci_id=0000:00:02.0
```

```bash
kubectl apply -f manifests/intel/
```

It's the same Deployment name and the same PVC as the CPU version, so if you did the CPU path first this just rolls the pod over and the model is already downloaded.
<!-- /tab -->

<!-- tab:nvidia -->
Install NVIDIA's device plugin so the node advertises `nvidia.com/gpu`:

```bash
helm upgrade -i nvidia-device-plugin https://nvidia.github.io/k8s-device-plugin/stable/nvidia-device-plugin-0.20.1.tgz \
  --namespace nvidia --create-namespace
kubectl get node -o jsonpath="{.items[0].status.allocatable}"   # expect "nvidia.com/gpu":"1"
```

Or, for the full stack (device plugin, GPU feature discovery, DCGM metrics), the GPU Operator v26.7.2 with the driver and toolkit turned off, because the host already has them:

```bash
kubectl create namespace gpu-operator
kubectl label namespace gpu-operator pod-security.kubernetes.io/enforce=privileged --overwrite
helm upgrade -i nvidia-gpu-operator https://helm.ngc.nvidia.com/nvidia/charts/gpu-operator-v26.7.2.tgz \
  --namespace gpu-operator --wait \
  --set cdi.enabled=true --set driver.enabled=false --set toolkit.enabled=false
```

The standard `ollama/ollama` image includes the CUDA backend. `manifests/nvidia/10-ollama-cuda.yaml` is the CPU manifest plus a GPU limit and the `nvidia` runtime class:

```yaml
    spec:
      runtimeClassName: nvidia   # created by the GPU Operator / nvkind setup
      ...
          resources:
            requests:
              cpu: "4"
              memory: 4Gi
            limits:
              memory: 8Gi
              nvidia.com/gpu: 1
```

```bash
kubectl apply -f manifests/nvidia/
```

To check the GPU is actually being used, look for `library=CUDA` in the `inference compute` log line:

```bash
kubectl -n llm logs deploy/ollama | grep "inference compute"
```
<!-- /tab -->

<!-- tab:amd -->
AMD's device plugin advertises the GPU as `amd.com/gpu`:

```bash
kubectl apply -f manifests/amd/amdgpu-device-plugin.yaml
kubectl get node -o jsonpath="{.items[0].status.allocatable}"
```

![The AMD device plugin DaemonSet ready and the node advertising amd.com/gpu: 1](img/term-gpu-amd-plugin.png)

`"amd.com/gpu":"1"`. The cluster can see the GPU. `manifests/amd/amdgpu-device-plugin.yaml` is AMD's [k8s-ds-amdgpu-dp.yaml](https://github.com/ROCm/k8s-device-plugin) at tag v1.31.0.11, with the image pinned to `rocm/k8s-device-plugin:1.31.0.11`. The [AMD GPU Operator](https://github.com/ROCm/gpu-operator) (v1.5.1) is the heavier alternative if you also want metrics and node labelling.

Ollama publishes a ROCm build of the same image. `manifests/amd/10-ollama-rocm.yaml` is the CPU manifest with the image swapped to `ollama/ollama:0.40.13-rocm`, a GPU limit, and one extra setting:

```yaml
          env:
            - name: OLLAMA_KEEP_ALIVE
              value: "24h"
            - name: OLLAMA_NUM_PARALLEL
              value: "1"
            - name: OLLAMA_CONTEXT_LENGTH
              value: "8192"         # don't let Ollama size the context from 64 GiB of VRAM
          resources:
            requests:
              cpu: "4"
              memory: 4Gi
            limits:
              memory: 8Gi
              amd.com/gpu: 1
```

Why `OLLAMA_CONTEXT_LENGTH`? Ollama picks a default context window from how much GPU memory it sees, and on a Strix Halo it sees 64 GiB. On my first run it chose a 131,072-token context for a 3B model and reserved a 14 GiB KV cache to go with it, so a 2 GB model was holding 17 GB of GPU memory. Pinning the context to 8192 tokens dropped the KV cache to 896 MiB and the whole model to 3.1 GB, with no change in speed for normal chat. If you need long prompts, raise it.

```bash
kubectl apply -f manifests/amd/
```

The ROCm image is a separate, bigger download than the CPU one, so give the first pull some time.
<!-- /tab -->

The first start is slow because two big downloads happen back to back: the Ollama image (3.4 GB, 10m21s on my connection) and then the model (2 GB). Watch it with:

```bash
kubectl -n llm get pods -w
kubectl -n llm logs deploy/ollama -c pull-model -f
```

When it's done:

```text
$ kubectl -n llm get pods,svc,pvc
NAME                          READY   STATUS    RESTARTS   AGE
pod/ollama-555f9656c4-rrbkg   1/1     Running   0          16m

NAME             TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)   AGE
service/ollama   ClusterIP   10.96.231.199   <none>        80/TCP    16m

NAME                                  STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   ...
persistentvolumeclaim/ollama-models   Bound    pvc-f353ecaf-6860-4bb9-befc-78669359c084   20Gi       RWO            standard       ...
```

<!-- tab:cpu -->
![k9s showing the Ollama pod running on CPU](img/k9s-cpu-running.png)

The log line that tells you what Ollama is running on:

```text
$ kubectl -n llm logs deploy/ollama | grep "inference compute"
time=2026-11-02T11:46:14.148Z level=INFO source=types.go:50 msg="inference compute" id=cpu library=cpu compute="" name=cpu description=cpu libdirs=ollama driver="" pci_id="" type="" total="8.0 GiB" available="8.0 GiB"
```

`total="8.0 GiB"`: Ollama read the pod's memory limit, not the laptop's 62 GB. That's the cgroup doing its job.
<!-- /tab -->

<!-- tab:intel -->
![k9s showing the Ollama pod running with the Intel GPU](img/k9s-intel-running.png)

```text
$ kubectl -n llm logs deploy/ollama | grep -E "inference compute|Vulkan"
time=2026-11-02T11:51:27.174Z level=INFO source=types.go:32 msg="inference compute" id=0 filter_id=0 library=Vulkan compute=0.0 name=Vulkan0 description="Intel(R) Graphics (PTL)" libdirs=ollama,vulkan driver=0.0 pci_id=0000:00:02.0 type=iGPU total="46.7 GiB" available="41.8 GiB"
```

`library=Vulkan`, `Intel(R) Graphics (PTL)`. PTL is Panther Lake, so that's the Arc B390.
<!-- /tab -->

<!-- tab:amd -->
![k9s on the AMD desktop showing the Ollama pod running on Kubernetes v1.37.0](img/k9s-amd-running.png)

```text
$ kubectl -n llm logs deploy/ollama | grep "inference compute"
time=2026-11-02T12:39:28.200Z level=INFO source=types.go:32 msg="inference compute" id=0 filter_id=0 library=ROCm compute=gfx1151 name=ROCm0 description="Radeon 8060S Graphics" libdirs=ollama,rocm_v7_2 driver=0.0 pci_id=0000:c3:00.0 type=iGPU total="64.0 GiB" available="63.8 GiB"
```

`library=ROCm`, `compute=gfx1151`, `Radeon 8060S Graphics`. ROCm found the GPU from inside the pod with no `HSA_OVERRIDE_GFX_VERSION` hacks: the ROCm 7.2 runtime in the Ollama image supports gfx1151 directly.
<!-- /tab -->

---

## Step 4: expose it and call it

The Service gives Ollama a stable name inside the cluster (`ollama.llm.svc`, port 80). From your machine, port-forward to it. I used local port 8081 because 8080 was already taken; use whatever's free.

```bash
kubectl -n llm port-forward svc/ollama 8081:80 &
```

Ollama speaks the OpenAI API, so anything that can talk to OpenAI can talk to this:

```bash
time curl -s localhost:8081/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:3b","messages":[{"role":"user","content":"In one sentence, why run a model on Kubernetes at home?"}]}' | python3 -m json.tool
```

<!-- tab:cpu -->
```text
real 14.98s (first call, includes loading the model)
{
    "id": "chatcmpl-201",
    "object": "chat.completion",
    "created": 1793620013,
    "model": "llama3.2:3b",
    "system_fingerprint": "fp_ollama",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Running a model on Kubernetes at home allows for flexible and efficient management of machine learning workflows, enabling easy scalability, data distribution, and model versioning, all within a familiar and accessible environment."
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 38,
        "prompt_tokens_details": {
            "cached_tokens": 0
        },
        "completion_tokens": 39,
        "total_tokens": 77
    }
}
```

The second identical call took 5.84 seconds, because the model was already in memory.

![The chat completion and benchmark on the CPU path](img/term-cpu-test.png)
<!-- /tab -->

<!-- tab:intel -->
```text
real 16.51s (first call, includes loading the model)
Running a model on Kubernetes at home can enable efficient, scalable, and flexible testing and deployment of machine learning models, as well as provide a secure and isolated environment that can be easily replicated and shared, without the need for expensive cloud computing resources.
```

(I piped this one through a one-line Python filter to print just the answer.)
<!-- /tab -->

<!-- tab:amd -->
```text
$ curl -s localhost:8081/v1/chat/completions ... | jq -r .choices[0].message.content
Running a model on Kubernetes at home allows for low-cost, flexible, and portable deployment of AI and machine learning workloads, enabling efficient testing, training, and deployment of models on small-scale hardware before scaling up to larger cluster environments.
```

The first call, model load included, came back in 3.6 seconds.
<!-- /tab -->

<!-- tab:nvidia -->
Same request, same OpenAI-style response shape as the other paths.
<!-- /tab -->

### How fast is it?

`bench.sh` in the repo asks the same question three times through Ollama's native API and reads its own timing counters:

```bash
./bench.sh http://localhost:8081
```

<!-- tab:cpu -->
```text
run 1: prompt 38 tok @ 21.8 tok/s, generated 177 tok @ 7.3 tok/s
run 2: prompt 38 tok @ 277.6 tok/s, generated 178 tok @ 7.3 tok/s
run 3: prompt 38 tok @ 281.0 tok/s, generated 178 tok @ 7.3 tok/s
```

**7.3 tokens/sec** on 4 requested cores. Readable, but you'll be watching it type.
<!-- /tab -->

<!-- tab:intel -->
```text
run 1: prompt 38 tok @ 44.9 tok/s, generated 181 tok @ 21.0 tok/s
run 2: prompt 38 tok @ 579.2 tok/s, generated 182 tok @ 21.1 tok/s
run 3: prompt 38 tok @ 564.0 tok/s, generated 182 tok @ 21.1 tok/s
```

**21.1 tokens/sec**, about 2.9× the CPU path on the same laptop, same model, same pod limits. And the proof it's the GPU doing the work, not just a log line claiming so:

```text
$ kubectl -n llm logs deploy/ollama | grep -E "offload|Vulkan0"
llama_prepare_model_devices: using device Vulkan0 (Intel(R) Graphics (PTL)) (0000:00:02.0) - 42737 MiB free
load_tensors: offloading output layer to GPU
load_tensors: offloading 27 repeating layers to GPU
load_tensors: offloaded 29/29 layers to GPU
load_tensors:      Vulkan0 model buffer size =  1918.35 MiB
llama_kv_cache:    Vulkan0 KV buffer size =  3584.00 MiB
```

All 29 layers on the GPU.

![The Intel GPU test: chat answer, benchmark at 21 tok/s, and all 29 layers offloaded to Vulkan0](img/term-gpu-intel-test.png)
<!-- /tab -->

<!-- tab:amd -->
```text
run 1: prompt 38 tok @ 1800.3 tok/s, generated 177 tok @ 82.6 tok/s
run 2: prompt 38 tok @ 3277.0 tok/s, generated 179 tok @ 85.2 tok/s
run 3: prompt 38 tok @ 3087.2 tok/s, generated 179 tok @ 85.8 tok/s
```

**About 85 tokens/sec** (90 tok/s on an earlier run with Ollama's default context), more than 11× the CPU path on the laptop and 4× the Arc. Strix Halo's memory bandwidth is the reason. And the proof it's the GPU:

![The AMD test: chat answer, benchmark at about 85 tok/s, 8192 context, ROCm on gfx1151 and all 29 layers offloaded to ROCm0](img/term-gpu-amd-test.png)

`offloaded 29/29 layers to GPU`, `ROCm0 KV buffer size = 896.00 MiB` (it was 14,336 MiB before setting `OLLAMA_CONTEXT_LENGTH`), and `/api/ps` reports the model using 3.1 GB of GPU memory with an 8192-token context.
<!-- /tab -->

<!-- tab:nvidia -->
Check the `offloaded N/N layers to GPU` line in the logs (`kubectl -n llm logs deploy/ollama | grep offloaded`): if it says anything less than all layers, part of the model is on the CPU and you'll feel it.
<!-- /tab -->

---

## Step 5: the payoff, your model debugs your cluster with k8sgpt

This is what the rest of the guide has been building towards. You've got a model serving inside your cluster; now you put it to work on that cluster. First you'll see what k8sgpt finds on its own, then you'll hand its findings to the model you just deployed and let it explain them.

Every cluster breaks. The useful skill is getting from "it's not working" to the reason quickly. Let's break it on purpose with a typo in the image tag, which is about the most common thing that goes wrong:

```bash
kubectl -n llm set image deploy/ollama ollama=ollama/ollama:0.40.31
kubectl -n llm get pods
```

```text
deployment.apps/ollama image updated
NAME                      READY   STATUS             RESTARTS   AGE
ollama-685b446ccd-s7p2z   0/1     ImagePullBackOff   0          45s
```

Because the Deployment uses `Recreate`, the old pod is already gone. Your model is down.

![k9s showing the pod in ImagePullBackOff](img/k9s-imagepullbackoff.png)

The old way is `kubectl describe` and reading the events:

```text
$ kubectl -n llm describe pod/ollama-685b446ccd-s7p2z | sed -n '/Events:/,$p'
Events:
  Type     Reason     Age               From               Message
  ----     ------     ----              ----               -------
  Normal   Scheduled  45s               default-scheduler  Successfully assigned llm/ollama-685b446ccd-s7p2z to local-llm-control-plane
  Normal   Pulled     44s               kubelet            spec.initContainers{pull-model}: Container image "ollama/ollama:0.40.13" already present on machine and can be accessed by the pod
  ...
  Warning  Failed     3s (x3 over 41s)  kubelet            spec.containers{ollama}: Failed to pull image "ollama/ollama:0.40.31": rpc error: code = NotFound desc = failed to pull and unpack image "docker.io/ollama/ollama:0.40.31": failed to resolve reference "docker.io/ollama/ollama:0.40.31": docker.io/ollama/ollama:0.40.31: not found
  Warning  Failed     3s (x3 over 41s)  kubelet            spec.containers{ollama}: Error: ErrImagePull
```

k8sgpt does that across the whole namespace and joins up the knock-on effects. Install it (`brew install k8sgpt`, or grab the binary from the [releases page](https://github.com/k8sgpt-ai/k8sgpt/releases); I used v0.4.41), then:

```bash
k8sgpt analyze --kubeconfig ./kubeconfig --namespace llm
```

```text
AI Provider: AI not used; --explain not set

0: Deployment llm/ollama()
- Error: Deployment llm/ollama has 1 replicas but 0 are available with status running

1: Service llm/ollama()
- Error: Service has not ready endpoints, pods: [Pod/ollama-685b446ccd-s7p2z], expected 1

2: Pod llm/ollama-685b446ccd-s7p2z(Deployment/ollama)
- Error: Back-off pulling image "ollama/ollama:0.40.31": ErrImagePull: rpc error: code = NotFound desc = failed to pull and unpack image "docker.io/ollama/ollama:0.40.31": failed to resolve reference "docker.io/ollama/ollama:0.40.31": docker.io/ollama/ollama:0.40.31: not found
```

![k8sgpt analyze listing the Deployment, Service and Pod findings](img/term-k8sgpt-analyze.png)

No AI involved yet: those are k8sgpt's built-in analyzers. Three findings, and they tell the whole story: the pod can't pull, so the Deployment has nothing available, so the Service has no endpoints, so your curl hangs. Fix it and check again:

```bash
kubectl -n llm rollout undo deploy/ollama
kubectl -n llm rollout status deploy/ollama
k8sgpt analyze --kubeconfig ./kubeconfig --namespace llm
```

```text
deployment.apps/ollama rolled back
...
deployment "ollama" successfully rolled out
AI Provider: AI not used; --explain not set

No problems detected
```

(kubectl warns that `rollout undo` doesn't update the last-applied annotation. In real life, fix the YAML and `kubectl apply -f` it again.)

### Now let the model you just deployed explain the next one

This is the bit everything else was for. k8sgpt can send its findings to an LLM for an explanation, and you now have an LLM. Break something else, the classic first-day-with-gated-models mistake of referencing a Hugging Face token secret you never created (`manifests/break/missing-secret.yaml`):

```bash
kubectl apply -f manifests/break/missing-secret.yaml
k8sgpt auth add --backend ollama --model llama3.2:3b --baseurl http://localhost:8081
time k8sgpt analyze --kubeconfig ./kubeconfig --namespace llm --explain --backend ollama
```

![k8sgpt explaining a missing secret using the model running in the cluster](img/term-16-k8sgpt-explain.png)

Your cluster, diagnosed by a model running in your cluster, with nothing leaving your machine. A 3B model's advice is generic, but it's right, and it took 26 seconds on CPU. Clean up with `kubectl -n llm delete pod model-downloader`.

![k9s showing the model-downloader pod stuck in CreateContainerConfigError](img/k9s-missing-secret.png)

---

## Where next

You've now got the shape of it: a model server, a GPU exposed through a device plugin, a Service in front, and something to tell you when it breaks. Here's where the real-cluster versions of each piece live:

- **Dynamic Resource Allocation (DRA).** Device plugins only let a pod ask for "one GPU". DRA lets it ask for a GPU with particular properties, and share or partition it. It's the direction everything is moving: [Kubernetes v1.37 DRA updates](https://kubernetes.io/blog/2026/09/03/kubernetes-v1-37-dra-updates/), [DRA docs](https://kubernetes.io/docs/concepts/scheduling-eviction/dynamic-resource-allocation/). Intel already ships a DRA driver ([intel-resource-drivers-for-kubernetes](https://github.com/intel/intel-resource-drivers-for-kubernetes)), and `llmfit claim` can generate a ResourceClaim sized for a model.
- **Gateway API Inference Extension.** Once you've got more than one replica, round-robin load balancing is the wrong answer for LLMs. This routes on queue depth and KV-cache state: [gateway-api-inference-extension.sigs.k8s.io](https://gateway-api-inference-extension.sigs.k8s.io/).
- **KServe.** A proper serving layer: model CRDs, autoscaling, canaries. [kserve.github.io](https://kserve.github.io/website/).
- **llm-d.** Distributed inference on Kubernetes, built on vLLM and the inference gateway. It hit 1.0 in October: [llm-d.ai](https://llm-d.ai/).
- **Kueue.** Queueing and quotas for when several people or jobs want the same GPUs: [kueue.sigs.k8s.io](https://kueue.sigs.k8s.io/).
- **Sympozium.** Once you've got a model serving, the next thing you'll probably want is agents that use it. [Sympozium](https://github.com/sympozium-ai/sympozium) is another of my projects: a Kubernetes-native control plane for running and coordinating multi-agent systems, with agents in isolated workloads and policy as CRDs. It can point agents at an Ollama endpoint like the one you just built. It's early and under active development, so expect things to change.

---

## Cleaning up

```bash
kind delete cluster --name local-llm --kubeconfig ./kubeconfig
```

That removes the node container and everything in it, model included. Your other clusters and your main kubeconfig are untouched, because this one only ever lived in `./kubeconfig`.

---

## Versions

Versions verified on **2 November 2026**, against each project's latest release.

| Component | Pinned here | Notes |
|---|---|---|
| kind | v0.33.0 | latest release |
| Kubernetes (kind node image) | v1.37.0, `kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5` | newest kind node image; upstream Kubernetes is v1.37.2 |
| kubectl | v1.37.2 | latest release; any 1.36 to 1.38 client works against a 1.37 server |
| Ollama | 0.40.13 (`ollama/ollama:0.40.13`, `:0.40.13-rocm`) | latest release |
| llmfit | 1.1.18 | latest release ([github.com/AlexsJones/llmfit](https://github.com/AlexsJones/llmfit)) |
| k8sgpt | 0.4.41 | latest release |
| k9s | v0.51.0 | latest release |
| Intel GPU device plugin | v0.37.1 | latest release |
| NVIDIA device plugin | 0.20.1 | latest release |
| NVIDIA GPU Operator | v26.7.2 | latest release |
| AMD (ROCm) device plugin | 1.31.0.11 | latest release |
| AMD GPU Operator | v1.5.1 | latest release |

---

## Spotted something wrong? Tell me

If a step didn't work for you, or you ran it on different hardware and want to tell me how it went, use the [contact form on axjns.dev](https://axjns.dev/#contact).

[Edit this page on GitHub](https://github.com/AlexsJones/axjns-k8s-local-llm/edit/main/README.md) · [Contributing](https://github.com/AlexsJones/axjns-k8s-local-llm/blob/main/CONTRIBUTING.md)
