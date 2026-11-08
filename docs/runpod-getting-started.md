# Runpod — Getting Started

_Last updated: 2026-11-07_

This guide takes you from no account to a running NVIDIA GPU Pod on Runpod: create the account, add funds, make an SSH key, create a bare-Ubuntu template, launch the Pod, log in, install the benchmark suite, and tear everything down afterwards. It is written for the NVIDIA workloads (201–232 on Ubuntu 24.04, 401–432 on Ubuntu 26.04). For the AMD workloads, use [`amd-developer-cloud-getting-started.md`](amd-developer-cloud-getting-started.md).

> **Conventions used below**
> - `<username>` — your Windows account name
> - `<POD_IP>` and `<SSH_PORT>` — the public IP address and SSH port shown in your Pod's **Connect** panel. Runpod maps the Pod's port 22 to a different public port, so you always need both.
> Replace these placeholders with your own values.
>
> Commands are shown for Windows PowerShell, and for Git Bash where a step uses `scp` or the suite's scripts. On macOS or Linux the same commands work in a terminal; use `~/.ssh/…` wherever this guide says `C:\Users\<username>\.ssh\…`. In Git Bash, `~/.ssh/…` is that same folder.

### What a Pod is (and why some results read `na`)

A Runpod Pod is a **container** on a shared GPU host, not a full virtual machine. You get root inside the container and the host's NVIDIA driver, which is everything the GPU workloads need. A few system-level measurements are not allowed inside a container, so those workloads finish normally and report `na` with the reason, or measure something narrower:

| Workloads | What the container prevents |
|---|---|
| x02 GPU health | Reading the kernel log (`dmesg`), so the GPU fault count is `na`. |
| x06 fio | The NVMe drives are not visible; fio measures the Pod's container disk instead. |
| x09, x10 NUMA | Setting a NUMA memory policy (`numactl`), so remote-memory latency is `na`. |
| x11 Linux perf | Reading CPU performance counters, so the PMU metrics are `na`. |
| x16 NCCL | Needs at least two GPUs; on a 1-GPU Pod the bandwidth metrics are `na`. |

A Pod also cannot restart itself, which the NVIDIA workloads never need.

### Prerequisites

- An SSH client: `ssh`, `ssh-keygen`, and `scp` on your PATH. Windows 10/11 include the OpenSSH client; if a command isn't found, add the "OpenSSH Client" optional feature in Settings. [Git for Windows](https://gitforwindows.org/) provides Git Bash, which the suite's laptop scripts use. macOS and Linux have everything already.
- A payment card. Runpod is prepaid: you add funds, and running Pods draw them down.
- An email address you can access to complete verification.
- Optional but recommended: a free [Docker Hub](https://hub.docker.com/) account (see [Docker Hub pull limits](#docker-hub-pull-limits)).

---

## 1. Create an account and add funds

1. Go to <https://www.runpod.io/> and click **Get Started**.
2. Sign up with your email address, and complete the verification email.
3. Answer the short background questions. When asked what you want to use, choose **Pods** (the other choices are Serverless, Clusters, and Public endpoints).
4. **Enable multi-factor authentication** when the console offers it (the yellow "Secure your account" banner). Your account holds a card and funds, so it is worth protecting.
5. Open **Billing** in the left menu and add funds. The balance shows at the top right of the console. Runpod credits are not refundable, so start with an amount that covers your planned runs: a full smoke, baseline, and extended run of one bundle takes about 6 hours of GPU time.
6. Still on **Billing**, consider turning on a **Low balance alert**, and auto-pay if you want long runs to continue without watching the balance.

> **If your balance reaches $0, Runpod stops all of your running Pods, and a Pod without a network volume is terminated: its data cannot be recovered.** Copy results off before the balance runs low (see [Tearing down](#7-tearing-down)). New accounts also have a default spending limit of $80 per hour, which a 1-GPU Pod is well under.

---

## 2. Generate an SSH key

You need an SSH key pair to log into your Pod.

> **Important:** an SSH key pair has two files. The `.pub` file is your **public** key — that's the one you add to Runpod. The file *without* `.pub` is your **private** key — keep it on your local machine and never paste it into any web form, repository, or chat. **Use a passphrase** so that even if the private key file is stolen it isn't immediately usable.

Open PowerShell and run `ssh-keygen`. The `-C` comment labels the key so you can recognise it in Runpod's settings:

```text
PS> ssh-keygen -t ed25519 -C "runpod-ssh-key" -f C:\Users\<username>\.ssh\runpod-ssh-key
Generating public/private ed25519 key pair.
Enter passphrase (empty for no passphrase): ********
Enter same passphrase again:                ********
Your identification has been saved in C:\Users\<username>\.ssh\runpod-ssh-key
Your public key has been saved in C:\Users\<username>\.ssh\runpod-ssh-key.pub
The key fingerprint is:
SHA256:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX runpod-ssh-key
The key's randomart image is:
[randomart omitted]
```

This produces two files in `C:\Users\<username>\.ssh\`:

| File | What it is | Where it goes |
|------|------------|---------------|
| `runpod-ssh-key`     | **Private** key | Stays on your local machine. Never share. |
| `runpod-ssh-key.pub` | **Public** key  | Added to your Runpod account (next section). |

**Avoid retyping the passphrase.** Load the key into the OpenSSH agent once at the start of a terminal session; later `ssh` and `scp` commands from that session, including the suite's laptop scripts, use it without asking again:

```text
PS> ssh-add C:\Users\<username>\.ssh\runpod-ssh-key
```

In Git Bash, start an agent first: `eval "$(ssh-agent -s)"`, then `ssh-add ~/.ssh/runpod-ssh-key`.

### Only for remote validation from your PC: a no-passphrase automation key

*Lab technicians who log in and run the suite on the Pod can skip this subsection.* You need an unattended key only when a program on your PC (for example an AI coding agent doing remote validation for the generator) must connect to the Pod over SSH with nobody there to type a passphrase. For that, create a **separate key pair** with no passphrase rather than removing the passphrase from your main key:

```text
PS> ssh-keygen -t ed25519 -C "runpod-automation" -N '""' -f C:\Users\<username>\.ssh\runpod-automation
```

(On macOS or Linux: `ssh-keygen -t ed25519 -C "runpod-automation" -N "" -f ~/.ssh/runpod-automation`.) Add `runpod-automation.pub` to Runpod as a second public key (next section). Because it is a different key, you can remove it from Runpod on its own without touching your main key. Keep it only in `.ssh\`, use it for nothing else, and delete it when you no longer need it.

---

## 3. Add your public key to Runpod

1. In the Runpod console, open **Settings** in the left menu (on some consoles the field is under **Credentials** instead).
2. Find the **SSH Public Keys** field.
3. Open your **public** key file in Notepad: `C:\Users\<username>\.ssh\runpod-ssh-key.pub` (note the `.pub` — make sure you are not opening the private key by mistake).
4. Copy the whole line and paste it into the field. It starts with `ssh-ed25519` and ends with the comment, for example `runpod-ssh-key`. Keep the `ssh-ed25519` at the front; without it, Runpod does not recognise the key.
5. Save. Runpod adds this key to every Pod you create from now on; Pods that already exist keep the keys they started with.

---

## 4. Create a bare-Ubuntu template

The suite installs the CUDA stack and every workload's software itself, so it starts from a plain Ubuntu image of the release your bundle targets. A **template** saves those Pod settings once, so every later Pod is a few clicks. Create one template per Ubuntu release you plan to use.

1. Open **Templates** in the left menu and click **New Template**. The **Create template** form opens on its **Config** tab.
2. Fill in:
   - **Template name:** for example `ubuntu-2404-bare-500GB` (and later `ubuntu-2604-bare-500GB`).
   - **Template type:** Pods.
   - **Compute type:** NVIDIA, GPU.
   - **Container image:** `ubuntu:24.04` for workloads 201–232, or `ubuntu:26.04` for 401–432.
   - **Select registry authentication:** leave it unset for now, or pick your Docker Hub credential if you added one (see [Docker Hub pull limits](#docker-hub-pull-limits)).
   - **Start command:** click **+ Start command** and paste the line below. A plain Ubuntu image has no SSH server, so this installs one, creates the server's host keys, writes your public key into `authorized_keys`, and then runs the SSH server as the Pod's main process (if SSH can't start, the Pod log shows why):

     ```sh
     bash -c 'apt-get update && apt-get install -y openssh-server sudo curl && mkdir -p /var/run/sshd /root/.ssh && echo "$PUBLIC_KEY" > /root/.ssh/authorized_keys && chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys && ssh-keygen -A && exec /usr/sbin/sshd -D -e'
     ```

     Runpod sets `$PUBLIC_KEY` to the keys you added in section 3, so the template works for any account and needs no editing when you change keys. (You may instead write one public key directly in place of `$PUBLIC_KEY`; a public key is not secret.)
   - **Storage configuration → Container disk:** **500** GB (the default is 5). The suite downloads several large models and Python environments; a small disk fills up partway through a run. As the form says, this disk is erased when the Pod is stopped.
   - **Storage configuration → Persistent storage (Volume disk):** **0** GB. Everything lives on the container disk, so nothing is left billing after you terminate the Pod.
   - **Networking configuration:** expose TCP port **22**. This is what makes "SSH over exposed TCP" and `scp` work.
   - **Environment variables:** none needed. You can add `HF_TOKEN` here later if a model's Hugging Face license requires it.
3. Leave the **GPU Compatibility** and **README** tabs as they are, and click **Create**. The template appears under **My templates** when you deploy a Pod.

> Runpod's ready-made templates (for example "Runpod PyTorch") already include SSH, but they ship their own CUDA and Python stack, which the suite's setup is not meant to run on top of. Use the bare-Ubuntu template for benchmark runs.

---

## 5. Create your first Pod

1. Open **Pods** in the left menu and click **Deploy**.
2. Under **Workload**, click **Explore all** (or the template search box), open **My templates**, and select your bare-Ubuntu template for the release you need.
3. **Pod name:** something you'll recognise, for example `mypod_2404_H100_NVL_20261107`.
4. **Region:** leave **Any region** unless you need a specific one.
5. Under **Compute**, on the **GPU** tab, pick a GPU. Type `h100` in the search box to narrow the list. Each card shows the price per hour, GPU memory, and how many GPUs one Pod can have; skip cards marked **Out of capacity**. Cards listed under **Incompatible** cannot run your template (for example, AMD MI300X shows there for these Ubuntu templates; use the AMD Developer Cloud for AMD).
6. Leave the GPU count at **1** and the pricing at **On-Demand**, then click **Deploy**.

> **Billing note:** Pods are billed per second for compute and storage. **Stopping** a Pod ends the GPU charge, but any volume disk keeps being billed (at a higher storage rate while stopped), and the **container disk is wiped** — with this template, that is where the suite, its installs, and your results live. Only **terminating** the Pod ends all charges, and terminating deletes everything on it. So don't stop a Pod to pause a run: copy your results off and then terminate (see [Tearing down](#7-tearing-down)).

When the Pod's status turns green on the **Pods** page, it's running. If the first start takes long or fails while pulling `ubuntu:26.04`, see [Docker Hub pull limits](#docker-hub-pull-limits).

---

## 6. Log in, install, and run the suite

1. On the **Pods** page, open your Pod and click **Connect**.
2. Copy the command under **SSH over exposed TCP**. Use this one rather than the basic "SSH" proxy command: only the exposed-TCP connection supports `scp` and the suite's laptop scripts. It looks like this; add `-i` and your private key if Runpod left it out:

   ```text
   PS> ssh root@<POD_IP> -p <SSH_PORT> -i C:\Users\<username>\.ssh\runpod-ssh-key
   ```

   The first time, SSH asks whether to trust the Pod's host key. The Pod is new and you just copied its address from your own console, so type `yes`.
3. You are now root inside the Pod. Confirm the GPU is visible (the host provides the NVIDIA driver):

   ```text
   root@<pod-id>:~# nvidia-smi
   ```

4. Install the bundle for your Pod's Ubuntu release and run three short smoke tests. For Ubuntu 24.04 (workloads 201–232):

   ```bash
   apt-get update && apt-get install -y git tmux
   git clone --recurse-submodules https://github.com/garys-gpu-benchmarks/bundle-nvidia-ubuntu-2404 /opt/benchmarks
   cd /opt/benchmarks && ./run_benchmark_suite.sh --list
   ./run_benchmark_suite.sh -w 201,202,215 --smoke
   ```

   For Ubuntu 26.04 (workloads 401–432), clone `bundle-nvidia-ubuntu-2604` instead and use 401, 402, and 415 in the last line. The first run of each workload installs it, so it takes longer than later runs. For the AI model workloads (x23–x31), if a model's Hugging Face license requires it, accept the license there and run `export HF_TOKEN=hf_...` first.

For the full list of suite commands (all profiles, ranges of workloads, a long run inside `tmux`), see "After the install" in the profile README, [`github-profile-README.md`](github-profile-README.md), or run `./run_benchmark_suite.sh --help`. Run long jobs inside `tmux` so they survive a dropped SSH connection.

### Copying files and running commands from your PC

These run on your PC in Git Bash, not inside the Pod. They use the same IP, port, and key as your SSH command; note that `scp` spells the port option `-P` (capital), while `ssh` uses `-p`.

```bash
# Copy a folder from your PC to the Pod
scp -r -P <SSH_PORT> -i ~/.ssh/runpod-ssh-key  MyLocalFolder  root@<POD_IP>:/root/

# Copy a folder from the Pod to the current folder on your PC
scp -r -P <SSH_PORT> -i ~/.ssh/runpod-ssh-key  root@<POD_IP>:/root/outputs/  .

# Run one command on the Pod
ssh -p <SSH_PORT> -i ~/.ssh/runpod-ssh-key  root@<POD_IP>  "ls -la /opt/benchmarks"
```

### Troubleshooting

- **`Permission denied (publickey)`** — check that the `-i` path points to your *private* key (no `.pub`), that the public key in Runpod's settings starts with `ssh-ed25519`, and that you added it **before** creating the Pod (Pods only receive keys that existed when they started; create a new Pod after adding a key).
- **`Connection refused` or a timeout** — the Pod may still be starting, or still installing the SSH server from the template's start command; wait a minute and retry. If it persists, open the Pod's log: the start command stops at the first failed step and shows why. Also confirm the template exposes TCP port 22 and you used the IP **and** port from the "SSH over exposed TCP" line.
- **`WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!`** — a new Pod was given an IP and port you used before. Confirm in the console that the old Pod is gone, then clear the stale entry and reconnect: `ssh-keygen -R "[<POD_IP>]:<SSH_PORT>"`.

### Docker Hub pull limits

Creating a Pod downloads its container image (`ubuntu:24.04` or `ubuntu:26.04`) from Docker Hub. Docker Hub limits anonymous downloads, so a Pod can fail to start, or start slowly, with a "rate limit" or "too many requests" message. Signing the download in with your own Docker Hub account avoids that:

1. In Docker Hub, open **Account Settings → Personal access tokens** and create a **read-only** access token. Use the token, not your Docker Hub password.
2. In the Runpod console, open **Credentials**, go to **Container Registry Auth**, and click **Add Credential**. Enter a name (for example `dockerhub`), your Docker Hub username, and the access token. Save.
3. Edit your bare-Ubuntu template, click **Select registry authentication**, choose that credential, and save. New Pods from the template now download the image signed in.

---

## 7. Tearing down

1. **Copy your results off first.** Terminating the Pod deletes everything on it. From your PC, clone [`gpu-bench-suite`](https://github.com/garys-gpu-benchmarks/gpu-bench-suite) and, in Git Bash, run:

   ```bash
   ./get_benchmark_results.sh --host <POD_IP> --port <SSH_PORT> -i ~/.ssh/runpod-ssh-key -o ~/results
   ```

   It copies the runtime ledger, every workload's results, and the suite logs.
2. On the **Pods** page, open the Pod's menu and **Terminate** it. **Stop** is not the same: a stopped Pod wipes its container disk but can keep billing for storage.
3. Check the **Pods** page to confirm it's gone, and the balance at the top right to confirm the charges stopped.
4. Your templates, SSH public keys, and registry credential stay in your account at no charge, ready for the next Pod. If you made an automation key (section 2) and no longer need it, delete `runpod-automation` and `runpod-automation.pub` from `.ssh\` and remove the public key from Runpod's settings.
