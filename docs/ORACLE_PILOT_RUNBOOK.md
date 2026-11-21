# Hosting pilot on Oracle Cloud Always Free

**Parked 2026-11-21.** Oracle requires a payment card for identity verification
at signup (no bypass; prepaid and virtual cards are refused), and the project is
still personal. No hosting move is planned for now.

The measurements below are what would justify revisiting it: a warm signed-in
page costs about 1.3 s, of which ~1.2 s is PHP building the HTML on the shared
host, whose CPU share varies by a factor of two between requests. Everything
else on the page — session check, database reads, cached repeats — is already
under 300 ms.

If it is revisited, the card-free alternative worth trying first is the
alwaysdata free plan (PHP, SSH, France, no card, personal use), measured with
`tools/measure_authenticated_page.py` against the same Supabase project.

Goal: run the **same PHP site** on a VM and measure it against the live host.
Nothing changes for users until the copy is proven. Supabase stays where it is.

Do these in order. Steps 1–2 are yours (they need your identity and a card for
verification, never charged). From step 3 I can do the work if you give me SSH
access.

## 1. Create the account

1. <https://signup.cloud.oracle.com> — free tier, card required for identity
   verification only.
2. Pick a home region close to Morocco: **Paris** or **Marseille** is the natural
   choice for latency; Ireland is where Supabase lives, so the PHP→database hop
   is shorter there. Paris wins for you, Ireland wins for the database — pick
   **Paris** and we measure both.

## 2. Create the VM

Always Free Ampere A1 is **2 OCPU / 12 GB** (cut from 4/24 in June 2026), plus
the x86 micro shapes. Either is enough.

- Shape: `VM.Standard.A1.Flex`, 2 OCPU, 12 GB — or `VM.Standard.E2.1.Micro` if
  ARM capacity is refused.
- Image: Ubuntu 24.04.
- Add your SSH public key at creation. Keep the private key on your machine.
- Open ports 80 and 443 in the subnet's security list (Oracle blocks them by
  default; the OS firewall also needs `ufw allow`).

**Capacity note:** "Out of host capacity" for A1 is common in popular regions.
Retry later, try another availability domain, or fall back to the micro shape.

## 3. Install the runtime (I do this)

```bash
sudo apt update && sudo apt install -y nginx php8.3-fpm php8.3-curl php8.3-json \
  php8.3-mbstring certbot python3-certbot-nginx git unzip
sudo ufw allow 'Nginx Full' && sudo ufw allow OpenSSH
```

## 4. Put the site on it (I do this)

```bash
sudo mkdir -p /var/www/myinterpreter
sudo chown $USER:www-data /var/www/myinterpreter
git clone https://github.com/RedaAlami02/myInterpreter.git /var/www/myinterpreter
```

Then copy the two **gitignored** config files from the workstation — they are
not in the repo and the site will not start without them:

- `config/supabase.local.php` (backend selector, project URL, publishable key,
  admin user id)
- `config/sources.php` (upstream endpoints)

These never go in git and never into a public directory listing.

## 5. Prove it before touching DNS

- Serve it on the VM's IP: `http://<vm-ip>/index.php`.
- Sign in, open `portfolio.php?timing=1`, capture the timing comment **twice**.
- Compare with the InfinityFree numbers: warm page ≈ 1.1 s, of which ≈ 0.77 s is
  PHP building the HTML. On the VM the same page should land under ~0.4 s.
- Check `handlers/live_quotes.php` returns 401 signed out and JSON signed in.

Only if it is clearly faster and fully working:

## 6. Switch

- Point DNS at the VM, `sudo certbot --nginx -d <domain>` for HTTPS.
- Keep InfinityFree running for a week as the fallback; reverting is a DNS
  change, and the FTP deploy path stays valid.

## 7. Keep it alive

Oracle reclaims an Always Free instance when **CPU, network and memory are all
below 20% over any 7-day window**, and suspends accounts idle for 30 days.
A portfolio site with cron traffic clears the network metric; a small database
or monitoring container keeps memory above the threshold. Do not rely on a cron
ping alone — it barely moves the 95th-percentile CPU figure.

## What this does not fix

The Supabase round trips stay as they are (Ireland). If the VM is fast but the
page still stalls, the next step is measuring the PHP→Supabase hop from Paris
versus Ireland, not more code.
