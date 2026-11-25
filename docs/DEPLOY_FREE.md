# Deploy InvoiceFlow for free

This guide puts the full stack (web, API, worker, Postgres, Redis, HTTPS) on free services. Total cost: ₪0 a month.
It follows the production setup in [DEPLOYMENT.md](DEPLOYMENT.md), with free providers filled in.

| Need | Free service | Free limit |
|---|---|---|
| Server | Oracle Cloud **Always Free** (ARM, Ampere A1) | up to 4 CPUs, 24 GB RAM, 200 GB disk, no time limit |
| Web address | **DuckDNS** subdomain (`yourname.duckdns.org`) | free forever |
| HTTPS certificate | Caddy + Let's Encrypt (already in the stack) | free |
| Documents and backups | **Backblaze B2** (S3-compatible, encrypted at rest) | 10 GB |
| Email (invitations, password resets) | **Brevo** | 300 emails a day |
| AI | **Groq** free API key (or offline mode, no key) | daily quota |
| Uptime alerts | **UptimeRobot** | 50 monitors |

You will need: a credit card for Oracle's identity check (Always Free resources are not charged), a GitHub login,
and about 1–2 hours. Commands marked PowerShell run on your Windows computer; everything else runs on the server.

---

## 1. Create the Oracle Cloud account

1. Go to <https://www.oracle.com/cloud/free/> → **Start for free**.
2. **Home region:** choose **Israel Central (Jerusalem)** if it is offered, so customer data stays in Israel. The home
   region cannot be changed later, and Always Free servers run only there. If Jerusalem has no free ARM capacity when
   you create the server (step 3), a European region such as Germany Central (Frankfurt) is the usual fallback;
   update the hosting line in the legal pages to match (step 11).
3. Finish the card check. Oracle reserves a small amount and releases it; Always Free use is not billed.
4. Recommended: **Billing → Budgets → Create budget** of USD 1 with an email alert, so you hear about any charge.

## 2. Make an SSH key (PowerShell, on your computer)

```powershell
ssh-keygen -t ed25519 -f $HOME\.ssh\invoiceflow -C invoiceflow
```

```powershell
Get-Content $HOME\.ssh\invoiceflow.pub
```

Copy the line it prints (starts with `ssh-ed25519`). Never share the file without `.pub`.

## 3. Create the server

1. Oracle console → **Compute → Instances → Create instance**.
2. Name: `invoiceflow`.
3. **Image and shape → Edit:**
   - Image: **Canonical Ubuntu 24.04** (the aarch64 build is selected automatically for ARM).
   - Shape: **Ampere → VM.Standard.A1.Flex**, **4 OCPUs**, **24 GB memory**. The "Always Free-eligible" label must show.
4. **Networking:** keep "Create new virtual cloud network", and **Assign a public IPv4 address**.
5. **Add SSH keys → Paste public keys:** paste the line from step 2.
6. **Boot volume:** set size to **100 GB**.
7. **Create.** If it says "Out of capacity", try again later or pick another availability domain; free ARM capacity
   frees up through the day.
8. When it is running, copy its **Public IP address**.

## 4. Open the web ports

Oracle blocks traffic in two places.

1. **Cloud firewall:** on the instance page → the subnet link → **Security Lists → Default Security List →
   Add Ingress Rules**: source `0.0.0.0/0`, protocol TCP, destination port `80`. Add a second rule for port `443`.
2. **Server firewall:** connect (PowerShell):

   ```powershell
   ssh -i $HOME\.ssh\invoiceflow ubuntu@<PUBLIC_IP>
   ```

   then on the server:

   ```bash
   # the rules must come before Oracle's catch-all REJECT rule, so insert them at its position
   pos=$(sudo iptables -L INPUT --line-numbers -n | awk '/REJECT/ {print $1; exit}')
   sudo iptables -I INPUT "$pos" -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo iptables -I INPUT "$pos" -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo netfilter-persistent save
   sudo iptables -L INPUT -n --line-numbers   # 80 and 443 must appear above REJECT
   ```

## 5. Get a free web address

1. Go to <https://www.duckdns.org>, sign in with GitHub, and create a subdomain, for example `invoiceflow-demo`.
2. Put the server's public IP in the **current ip** box → **update ip**.
3. Your address is now `invoiceflow-demo.duckdns.org`. (A paid domain such as `.co.il` looks more professional and
   lets you verify email properly; you can switch later by changing three `.env` values.)

## 6. Install Docker and get the code (on the server)

```bash
sudo apt-get update && sudo apt-get -y upgrade
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && newgrp docker
```

Clone the repository. If it is private, create a GitHub **fine-grained personal access token** with read-only
"Contents" access to this repository, and use it as the password when Git asks:

```bash
git clone https://github.com/<your-user>/<your-repo>.git invoiceflow
cd invoiceflow
```

## 7. Storage and backups: Backblaze B2

1. Sign up at <https://www.backblaze.com/cloud-storage> (B2 Cloud Storage, free 10 GB).
2. **Buckets → Create a Bucket:** name `invoiceflow-docs-<random>`, **Private**, **Default Encryption: Enable**.
3. Create a second bucket `invoiceflow-backups-<random>`, Private, encryption on. In its **Lifecycle Settings**, keep
   only the last 35 days of versions.
4. **Application Keys → Add a New Application Key:** allow access to both buckets, Read and Write. Copy the
   **keyID** and **applicationKey** now (the key is shown once).
5. Note the bucket's **Endpoint**, for example `s3.eu-central-003.backblazeb2.com`.

## 8. Email: Brevo

1. Sign up at <https://www.brevo.com> (free plan).
2. **Senders, domains & dedicated IPs → Senders → Add a sender:** use an address you own and confirm it.
3. **SMTP & API → SMTP:** copy the login and create an **SMTP key**.

With a DuckDNS address you cannot add the SPF/DKIM records a domain would need, so some emails may land in spam.
That is fine for a demo; with your own domain, verify it in Brevo and add the records it shows.

## 9. AI: Groq (free)

Create a key at <https://console.groq.com/keys>. Without any key the app still works in offline mode. If you add an
OpenAI key later, keep auto-recharge off and the daily budgets below.

## 10. Configure and start

On the server, in the `invoiceflow` folder:

```bash
cp .env.example .env
openssl rand -hex 24   # run three times: JWT_SECRET, POSTGRES_PASSWORD, APP_DB_PASSWORD
nano .env
```

Set these values (replace everything in `<>`):

```dotenv
SITE_ADDRESS=invoiceflow-demo.duckdns.org
APP_BASE_URL=https://invoiceflow-demo.duckdns.org
CORS_ORIGINS=["https://invoiceflow-demo.duckdns.org"]
JWT_SECRET=<random 1>
POSTGRES_PASSWORD=<random 2>
APP_DB_PASSWORD=<random 3>

S3_ENDPOINT_URL=https://<b2 endpoint>
S3_ACCESS_KEY=<keyID>
S3_SECRET_KEY=<applicationKey>
S3_BUCKET=<invoiceflow-docs-...>
S3_SSE=AES256

BACKUP_S3_URI=s3://<invoiceflow-backups-...>/invoiceflow
BACKUP_S3_ACCESS_KEY=<keyID>
BACKUP_S3_SECRET_KEY=<applicationKey>
BACKUP_S3_ENDPOINT=https://<b2 endpoint>
BACKUP_S3_REGION=auto

SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=<brevo smtp login>
SMTP_PASSWORD=<brevo smtp key>
EMAIL_FROM=InvoiceFlow <your-confirmed-sender@example.com>

OPENAI_API_KEY=<groq key, or leave empty for offline mode>
AI_PAID_DAILY_TOKEN_BUDGET=300000
RATE_LIMIT_AI_PER_DAY=40
ALLOW_SIGNUP=true
```

Keep `JWT_SECRET` the same forever: two-factor secrets are encrypted with a key derived from it.

Start everything (the first build takes 10–20 minutes on ARM):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Check it: open `https://invoiceflow-demo.duckdns.org/health/ready` in your browser; it should answer `ok`. Caddy
gets the HTTPS certificate on the first visit. If the page does not load, see Troubleshooting below.

## 11. Before you share the link

1. **Legal details.** The operator details are in `frontend/src/lib/legal.ts` (InvoiceFlow as an independent project,
   contact email, hosting "Oracle Cloud, Jerusalem"). Change them there if they change, then rebuild the web app:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build web
   ```

2. **"Try the demo".** Visitors who don't want an account get a private copy of the demo company, deleted after 24
   hours; nobody sees another visitor's uploads. Prepare it once, then lock the demo company's shared accounts (their
   password is published in the repository, and anyone who signed in could change what every visitor gets):

   ```bash
   docker compose exec api python -m app.cli seed --reset
   docker compose exec api python -m app.cli lock-demo-template
   ```

   Run `seed --reset` only on a fresh install: it resets all data, including real sign-ups. Each visitor address can
   open 5 demos a day (`RATE_LIMIT_DEMO_PER_DAY`), and the AI question limit per visitor still applies.
3. **Sign-up.** Keep `ALLOW_SIGNUP=true` so businesses can create a real, private account, or set it to `false` and
   run the start command again to offer only the demo.
4. **Uptime alerts.** At <https://uptimerobot.com> add two HTTP monitors with email alerts:
   `https://<address>/health/ready` and `https://<address>/health/alerts`.

## 12. Updating later

```bash
cd ~/invoiceflow && git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Migrations run automatically when the API starts.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Browser cannot reach the site | Check both firewalls (step 4) and that DuckDNS shows the current IP. |
| Certificate error right after start | Wait a minute and reload: Caddy is still getting the certificate. `docker compose logs caddy` shows progress. |
| `set ... ` error on start | A required `.env` value is missing; the message names it. |
| Uploads fail | Check the B2 endpoint has `https://`, the key can reach the docs bucket, and encryption is on. `docker compose logs api` |
| No emails arrive | Look in spam; confirm the Brevo sender; `docker compose logs worker`. |
| Server stopped by Oracle | Oracle may reclaim Always Free servers it considers idle (very low CPU for 7 days). Upgrading the account to Pay As You Go removes that rule while Always Free resources stay free; keep the USD 1 budget alert. |

## What stays manual

- Backups run daily to B2 automatically; run the monthly restore drill once (DEPLOYMENT.md, step 9 "Backups").
- Read the legal pages once with a lawyer before real customers sign up.
