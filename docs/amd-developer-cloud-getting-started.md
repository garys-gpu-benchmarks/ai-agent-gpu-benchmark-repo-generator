# AMD Developer Cloud — Getting Started

_Last updated: 2026-11-07_

This guide takes you from no account to a running AMD Instinct MI300X GPU droplet on the AMD Developer Cloud: create the account, get credits, make an SSH key, launch the droplet, log in, install the benchmark suite, and tear everything down afterwards. It is written for the AMD workloads (101–132 on Ubuntu 24.04, 301–332 on Ubuntu 26.04). For the NVIDIA workloads, use [`runpod-getting-started.md`](runpod-getting-started.md).

> **Conventions used below**
> - `<username>` — your Windows account name
> - `<hostname>` — your local machine's hostname
> - `<DROPLET_IP>` — the public IPv4 address shown in your droplet panel after it boots
> Replace these placeholders with your own values.
>
> Commands are shown for Windows PowerShell. On macOS or Linux the same commands work in a terminal; use `~/.ssh/…` wherever this guide says `C:\Users\<username>\.ssh\…`.

### Prerequisites

- An SSH client: `ssh` and `ssh-keygen` on your PATH. Windows 10/11 include the OpenSSH client; if either command isn't found, add the "OpenSSH Client" optional feature in Settings. macOS and Linux have it already.
- A payment card you can add to the account. A card on file is required to create a GPU droplet, even when credits will cover all of your usage.
- An email address you can access to complete verification.

---

## 1. Create an account and get credits

1. Go to <https://amd.digitalocean.com/>.
2. To the right of "Don't have an account?", click **Sign up**.
3. Check the box for "I agree to the Terms..." then click **Sign Up with Email**.
4. Enter your full name, email address, and password, then click **Sign Up**.
5. Open the verification email and click the link to finish creating your AMD Developer Cloud account.
6. Add a payment method when prompted. It is required before you can create a droplet, even if you only spend credits; credits are used first.
7. **Get complimentary credits.** There are two routes; neither is instant:
   - Join the free **AMD AI Developer Program** at <https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html>. Members receive AMD Developer Cloud credits (currently $100) and an activation code on the program's member site.
   - Or click the credit banner on the **Create GPU Droplet** page and fill in the request form.

   Approved credits usually arrive within three business days and show on the console's home page. **Credits expire**, so check the expiry date and plan your runs inside it. When complimentary credit runs out, AMD may remove the droplet and **everything on it**, so copy your results off well before then (see [Tearing down](#6-tearing-down)).
8. If you need more GPU capacity than your account allows by default, request a GPU limit increase. A reasonable "Reason for increase" is something like:
   > _"I am working on low-level programming and would like to evaluate AMD GPUs."_

---

## 2. Generate an SSH key

You need an SSH key pair to log into your droplet.

> **Important:** an SSH key pair has two files. The `.pub` file is your **public** key — that's the one you upload to the AMD Developer Cloud. The file *without* `.pub` is your **private** key — keep it on your local machine and never paste it into any web form, repository, or chat. **Use a passphrase** so that even if the private key file is stolen it isn't immediately usable.

Open PowerShell and run `ssh-keygen`:

```text
PS> ssh-keygen -t ed25519
Generating public/private ed25519 key pair.
Enter file in which to save the key (C:\Users\<username>\.ssh\id_ed25519): C:\Users\<username>\.ssh\amd-devcloud-key
Enter passphrase (empty for no passphrase): ********
Enter same passphrase again:                ********
Your identification has been saved in C:\Users\<username>\.ssh\amd-devcloud-key
Your public key has been saved in C:\Users\<username>\.ssh\amd-devcloud-key.pub
The key fingerprint is:
SHA256:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX <username>@<hostname>
The key's randomart image is:
[randomart omitted]
```

This produces two files in `C:\Users\<username>\.ssh\`:

| File | What it is | Where it goes |
|------|------------|---------------|
| `amd-devcloud-key`     | **Private** key | Stays on your local machine. Never share. |
| `amd-devcloud-key.pub` | **Public** key  | Uploaded to the AMD Developer Cloud (next section). |

**Avoid retyping the passphrase.** Load the key into the OpenSSH agent once at the start of a terminal session; later `ssh` commands from that session, including scripts you start from it, use it without asking again:

```text
PS> ssh-add C:\Users\<username>\.ssh\amd-devcloud-key
```

### Only for remote validation from your PC: a no-passphrase automation key

*Lab technicians who log in and run the suite on the droplet can skip this subsection.* When you run the suite on the droplet itself, a ROCm restart during setup is handled on the droplet: setup carries on by itself after the restart, and nothing on your PC needs to reconnect.

You need an unattended key only when a program on your PC (for example an AI coding agent doing remote validation for the generator) must reconnect to the droplet over SSH after it restarts, with nobody there to type a passphrase. For that, create a **separate key pair** with no passphrase. Do not copy your main key and strip its passphrase: that would leave your main key unencrypted on disk.

```text
PS> ssh-keygen -t ed25519 -N '""' -f C:\Users\<username>\.ssh\amd-devcloud-automation
```

(On macOS or Linux: `ssh-keygen -t ed25519 -N "" -f ~/.ssh/amd-devcloud-automation`.) Upload `amd-devcloud-automation.pub` as a second SSH key in section 3, and point the automation at it with `ssh -i …\amd-devcloud-automation …`. Because it is a different key, you can remove it from the AMD Developer Cloud on its own without touching your main key. Keep it only in `.ssh\`, use it for nothing else, and delete it (and remove its public key from the console) when the droplet is gone.

---

## 3. Create your first GPU droplet

1. Go to <https://amd.digitalocean.com/> and log in.
2. Click the green **Create** dropdown in the top navigation bar, then select **GPU Droplets**.
3. Click **Add SSH Key**.
4. Open your **public** key file in Notepad:
   ```
   C:\Users\<username>\.ssh\amd-devcloud-key.pub
   ```
   (Note the `.pub` extension — make sure you are not opening the private key by mistake.)
5. Copy the entire contents and paste them into the **SSH Key content** box.
6. Give the key a descriptive name, for example `MyAmdPublicKey-YYYYMMDD`.
7. On the **Create GPU Droplet** page, choose:
   - **GPU Plan:** the single-GPU **`MI300X`** plan — not **`MI300X x8`**, which sits directly above it in the list. Both are priced the same per GPU, but `x8` bills for all eight GPUs at once (8 times the hourly cost of the single-GPU plan) and uses up credits 8 times faster. The single-GPU droplet has one MI300X with 192 GB of GPU memory, 240 GiB of system memory, and 20 vCPUs.
   - **Image:** under the **Bare OS** tab (not **Quick Start**), select **Ubuntu → 24.04 (LTS) x64** for workloads 101–132, or **Ubuntu 26.04** for workloads 301–332 when the image list offers it. The suite installs ROCm itself on a bare Ubuntu image. The **`ROCm™ Software`** Quick Start image already ships ROCm plus a preconfigured Jupyter/Docker stack, which the suite's setup is not meant to run on top of.
   - **SSH Key:** the key you just added.
8. Note the price shown on the page before confirming.
9. Click **Create GPU Droplet** to launch.

> **Billing note:** GPU droplets are billed per second, with a 5-minute minimum, from the moment you create the droplet until you **destroy** it. Billing does not depend on whether you are using the GPU, and **powering a droplet off does not stop billing**: the GPU stays reserved for you. Only destroying the droplet ends the charges (see [Tearing down](#6-tearing-down)).

Wait a few minutes for the droplet to boot, then copy the **Public IPv4** address from the droplet panel — you'll need it next.

---

## 4. Log in to the droplet

Open PowerShell and SSH in with your private key. Enter your passphrase when prompted (unless you loaded the key with `ssh-add`).

The **first** time you connect to a given `<DROPLET_IP>`, SSH pauses before the passphrase prompt to ask whether the server's host key should be trusted:

```text
The authenticity of host '<DROPLET_IP> (<DROPLET_IP>)' can't be established.
ED25519 key fingerprint is SHA256:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

This is a real trust decision, not a formality — you're confirming the fingerprint belongs to your droplet and not to someone else who happens to be on that address. Before typing `yes`:

- Confirm `<DROPLET_IP>` in the prompt matches the Public IPv4 shown in your droplet panel.
- To verify the fingerprint itself, open the droplet's **Access** tab in the control panel, launch the **web console**, and run `ssh-keygen -l -f /etc/ssh/ssh_host_ed25519_key.pub`. The `SHA256:…` value it prints must match the one in the prompt.

Once you type `yes`, OpenSSH saves the fingerprint in `C:\Users\<username>\.ssh\known_hosts` and won't ask again for this IP — unless the fingerprint later changes (see Troubleshooting below).

```text
PS> ssh -i C:\Users\<username>\.ssh\amd-devcloud-key root@<DROPLET_IP>
Enter passphrase for key 'C:\Users\<username>\.ssh\amd-devcloud-key':
Welcome to Ubuntu 24.04.3 LTS (GNU/Linux 6.8.0-87-generic x86_64)

 * Documentation:  https://help.ubuntu.com
 * Management:     https://landscape.canonical.com
 * Support:        https://ubuntu.com/pro

System information as of <date>

root@<droplet-hostname>:~#
```

(Your Ubuntu point release and kernel version may differ from this example.)

> Because this is the **Bare OS** image rather than the **`ROCm™ Software`** Quick Start image, you get a plain Ubuntu login banner — no Jupyter server, no Docker container, no ROCm. That's expected: the suite's setup installs ROCm.

ROCm isn't installed yet, so `amd-smi` (and the older `rocm-smi`) won't exist at this point — that's not an error. Confirm the GPU is visible at the PCI level instead, which works with no GPU software installed. `1002` is AMD's PCI vendor ID, so this lists only AMD devices:

```text
root@<droplet-hostname>:~# lspci -d 1002: | grep -iE 'display|accelerator|processing'
```

You should see one line for the MI300X. That confirms the kernel sees the card before any driver is installed. If nothing shows up, the droplet was not provisioned correctly; that isn't something to fix in software, so contact AMD Developer Cloud support before going further.

### Troubleshooting

- **`Permission denied (publickey)`** — check that the `-i` path points to your *private* key (no `.pub`), and that the matching public key was added to the droplet in section 3.
- **Connection times out or is refused** — the droplet may still be booting; wait a minute and retry. If it persists, confirm you copied the Public IPv4 (not the private IP) from the droplet panel.
- **Prompted for a password instead of a passphrase** — this usually means the SSH key wasn't added to the droplet, or you're pointing at the wrong key file.
- **`WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!`** — the fingerprint saved for `<DROPLET_IP>` no longer matches what the server presents. This is expected if you destroyed your old droplet and a *new* one was given the same IP; IP addresses are reused. It can also mean something else is now listening on that IP. Only continue once you've confirmed in the control panel that the old droplet is gone and this new one is yours. Then clear the stale entry and reconnect:
  ```text
  PS> ssh-keygen -R <DROPLET_IP>
  ```
  You'll be asked to accept the new fingerprint on the next connection, as on a first connection.

---

## 5. Install and run the benchmark suite

On the droplet, as root, install `git`, clone the bundle for your platform into `/opt/benchmarks`, and check that every workload is ready. For AMD on Ubuntu 24.04 (workloads 101–132):

```bash
apt-get update && apt-get install -y git tmux
git clone --recurse-submodules https://github.com/garys-gpu-benchmarks/bundle-amd-ubuntu-2404 /opt/benchmarks
cd /opt/benchmarks && ./run_benchmark_suite.sh --list
./run_benchmark_suite.sh -w 101,102,115 --smoke
```

On Ubuntu 26.04 (workloads 301–332), clone `bundle-amd-ubuntu-2604` instead and use 301, 302, and 315 in the last line. The first smoke run of a workload installs it, including ROCm; ROCm setup may restart the droplet. When it does, log in again after a few minutes, and setup continues by itself.

After ROCm is installed, `amd-smi` shows the GPU's memory and utilization (`rocm-smi` still works as a fallback). For the full list of suite commands (all profiles, ranges of workloads, a long run inside `tmux`), see "Install on a GPU Host" and "After the install" in the profile README, [`github-profile-README.md`](github-profile-README.md), or run `./run_benchmark_suite.sh --help`.

---

## 6. Tearing down

1. **Copy your results off first.** Destroying the droplet deletes everything on it. From your PC, clone [`gpu-bench-suite`](https://github.com/garys-gpu-benchmarks/gpu-bench-suite) and run `./scripts/get_benchmark_results.sh --host <DROPLET_IP>` (Git Bash on Windows). It copies the runtime ledger, every workload's results, and the suite logs.
2. In the AMD Developer Cloud control panel, **destroy** the droplet. Powering it off is not enough: a powered-off droplet is still billed.
3. Check the droplets list to confirm it's gone.
4. If you made an automation key (section 2), delete `amd-devcloud-automation` and `amd-devcloud-automation.pub` from `.ssh\`, and remove its public key from the console.
