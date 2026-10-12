# Network Test & Tailscale Setup (H-P0-4)

**Goal:** every team laptop can reach the coordinator laptop on port 8000, on **campus Wi-Fi, home/hostel Wi-Fi and a phone hotspot**.

**Why Tailscale:** campus Wi-Fi usually blocks laptops from talking to each other (client isolation). Tailscale puts all team devices on a private, encrypted network that works through that, so the coordinator address stays the same on every network.

## 1. Set up Tailscale (all 6 machines)
1. Check the current free-plan limits on tailscale.com (users and devices). If 5 separate accounts don't fit, sign every device into **one shared team account**.
2. Install: Windows / macOS from tailscale.com/download; Ubuntu: `curl -fsSL https://tailscale.com/install.sh | sh` then `sudo tailscale up`.
3. Sign in on every machine. In the admin console, note each device's **100.x.y.z** address and turn on MagicDNS (gives names like `harith-laptop`).
4. Coordinator laptop: allow incoming connections on port 8000 when the firewall asks.
   - **Windows:** allow on **Private** networks.
   - **macOS:** click "Allow" on the first prompt.

## 2. Run the test
On the **coordinator** laptop:
```bash
python scripts/net_probe.py serve --port 8000
```
On **each other laptop**, on each network:
```bash
python scripts/net_probe.py check http://<coordinator-LAN-IP>:8000        # direct
python scripts/net_probe.py check http://<coordinator-tailscale-IP>:8000  # via Tailscale
```
Once the dispatcher runs (`idlegrid-dispatcher --host 0.0.0.0`), the same check works against it: it serves `/healthz` too.

## 3. Results (fill in)
Write `OK <median ms>` or `FAIL`.

| From laptop (owner, OS) | Campus Wi-Fi: direct | Campus Wi-Fi: Tailscale | Home Wi-Fi: direct | Home Wi-Fi: Tailscale | Hotspot: direct | Hotspot: Tailscale |
|---|---|---|---|---|---|---|
| Arya ( ) | | | | | | |
| Amaan ( ) | | | | | | |
| Rejish ( ) | | | | | | |
| Ronit ( ) | | | | | | |
| Harith (coordinator) ( ) | n/a | n/a | n/a | n/a | n/a | n/a |

**Coordinator address to use everywhere:** `http://__________:8000` (date tested: ____)

## 4. If something fails
| Symptom | Likely cause | Fix |
|---|---|---|
| Direct FAIL on campus, Tailscale OK | Client isolation | Expected: use the Tailscale address |
| Both FAIL | Coordinator firewall or probe not running | Check the probe window on the coordinator; allow Python through the firewall |
| Tailscale FAIL | Device not signed in, or signed into a different account | `tailscale status` on both machines |
| Works on hotspot only | Home router isolation ("AP isolation") | Use Tailscale, or turn off AP isolation |
