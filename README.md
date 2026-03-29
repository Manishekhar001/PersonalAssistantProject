# Personal Assistant — Complete Setup Guide

A Telegram-based personal assistant built with LangGraph + Groq, deployed on AWS EC2.

---

## What it can do

| Capability | How |
|---|---|
| General Q&A | Groq LLM directly |
| Web search | SerpAPI |
| Read & send Gmail | IMAP + SMTP (App Password) |
| Notes | Notion |
| Tasks | Notion |
| Calendar events | Notion |
| Expense tracking | SQLite (local) |

---

## PART 1 — Notion Setup (10 minutes)

You need to do this before running the bot.

### Step 1: Create a Notion Integration

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **"+ New integration"**
3. Give it a name: `Personal Assistant`
4. Click **Submit**
5. Copy the **"Internal Integration Token"** — this is your `NOTION_API_KEY`

---

### Step 2: Create 3 Databases + 1 Page in Notion

Open Notion and create the following:

#### A. Notes Page
1. Create a new **Page** in Notion (name it `Notes`)
2. Open it → click **Share** → search for `Personal Assistant` → click **Invite**
3. Copy the page URL: `https://notion.so/Notes-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
4. The ID is the last 32 characters: `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   → This is your `NOTION_NOTES_PAGE_ID`

#### B. Tasks Database
1. Create a new **Database (full page)** (name it `Tasks`)
2. Add these properties:
   - `Name` (title) — already exists
   - `Status` (select) — add options: `Not started`, `In progress`, `Done`
   - `Due Date` (date)
3. Click **Share** → invite `Personal Assistant`
4. Copy the database URL and extract the 32-char ID
   → This is your `NOTION_TASKS_DB_ID`

#### C. Calendar Database
1. Create a new **Database (full page)** (name it `Calendar`)
2. Add these properties:
   - `Name` (title) — already exists
   - `Date` (date)
   - `Description` (text)
3. Click **Share** → invite `Personal Assistant`
4. Copy the database URL and extract the 32-char ID
   → This is your `NOTION_CALENDAR_DB_ID`

> **How to find the ID from a URL:**
> URL: `https://notion.so/My-Calendar-abc123def456789012345678901234ab`
> ID:  `abc123def456789012345678901234ab`

---

## PART 2 — Gmail App Password (5 minutes)

Gmail requires an "App Password" instead of your regular password for IMAP/SMTP.

1. Go to [myaccount.google.com](https://myaccount.google.com)
2. Go to **Security** → **2-Step Verification** → enable it (required)
3. Go back to Security → search for **"App passwords"**
4. Click App passwords → choose **Mail** → choose **Other** → name it `Assistant`
5. Copy the 16-character password (format: `xxxx xxxx xxxx xxxx`)
   → This is your `GMAIL_APP_PASSWORD`

Also enable IMAP:
1. Open Gmail → Settings (gear icon) → See all settings
2. Go to **Forwarding and POP/IMAP** tab
3. Enable **IMAP Access** → Save

---

## PART 3 — AWS EC2 Setup (15 minutes)

### Step 1: Create an EC2 Instance

1. Go to [aws.amazon.com](https://aws.amazon.com) → sign in → go to **EC2**
2. Click **Launch Instance**
3. Settings:
   - Name: `personal-assistant`
   - AMI: **Ubuntu Server 22.04 LTS** (Free tier eligible)
   - Instance type: **t2.micro** (Free tier)
   - Key pair: Create new → name it `assistant-key` → download the `.pem` file
   - Security group: Allow **SSH (port 22)** from your IP
4. Click **Launch Instance**

### Step 2: Connect to EC2 via SSH

**On Windows (using PowerShell or Command Prompt):**
```bash
# Replace path and IP with yours
ssh -i "C:\Users\YourName\Downloads\assistant-key.pem" ubuntu@YOUR_EC2_PUBLIC_IP
```

**On Mac/Linux:**
```bash
chmod 400 ~/Downloads/assistant-key.pem
ssh -i ~/Downloads/assistant-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

> Find your EC2 Public IP in the EC2 console under "Instances"

---

### Step 3: Upload Your Project to EC2

**From your local machine** (run this in a new terminal, NOT the SSH session):

```bash
# On Windows (PowerShell):
scp -i "C:\Users\YourName\Downloads\assistant-key.pem" -r "C:\path\to\personal-assistant" ubuntu@YOUR_EC2_IP:~/

# On Mac/Linux:
scp -i ~/Downloads/assistant-key.pem -r /path/to/personal-assistant ubuntu@YOUR_EC2_IP:~/
```

---

### Step 4: Run Setup Script

Back in your SSH session:

```bash
cd ~/personal-assistant
bash deploy/setup.sh
```

This installs Python, creates a virtual environment, installs all packages, and sets up the bot as a system service.

---

### Step 5: Fill in Your API Keys

```bash
nano .env
```

Fill in all your values (Groq, Telegram, SerpAPI, Notion, Gmail).

To save in nano: `Ctrl+O` → Enter → `Ctrl+X`

---

### Step 6: Start the Bot

```bash
sudo systemctl start personal-assistant
```

Check it's running:
```bash
sudo systemctl status personal-assistant
```

You should see `Active: active (running)`.

---

## PART 4 — Test It

Open Telegram → search for your bot (by username you set with BotFather) → send `/start`

Try these messages:
- `What's the weather in Hyderabad today?`
- `Add expense 150 food lunch at dhaba`
- `Show my expenses`
- `Create a task: Review project report, due 2025-12-31`
- `What are my pending tasks?`
- `Create a note titled Meeting Notes: Discussed Q4 goals`
- `Schedule an event: Team call on 2025-12-20`

---

## Useful Commands (after deployment)

```bash
# View live logs
sudo journalctl -u personal-assistant -f

# Restart the bot (after making code changes)
sudo systemctl restart personal-assistant

# Stop the bot
sudo systemctl stop personal-assistant

# Check status
sudo systemctl status personal-assistant
```

---

## Project Structure

```
personal-assistant/
├── bot.py              ← Entry point. Runs the Telegram bot.
├── config.py           ← Reads all .env variables
├── agent/
│   ├── graph.py        ← LangGraph agent (the brain)
│   └── tools.py        ← All 11 tools the agent can call
├── data/
│   └── expenses.db     ← SQLite database (auto-created)
├── deploy/
│   └── setup.sh        ← EC2 setup script
├── requirements.txt
└── .env                ← Your secrets (never commit this!)
```

---

## Architecture

```
You (Telegram)
    ↓
bot.py (polling — no domain needed)
    ↓
LangGraph Agent (Groq LLM)
    ↓ decides which tool to call
┌───────────┬────────────┬──────────┬────────────┬─────────┐
│ web_search│ Gmail IMAP │  Notion  │   Notion   │ SQLite  │
│ (SerpAPI) │   + SMTP   │  Notes   │Tasks+Cal   │Expenses │
└───────────┴────────────┴──────────┴────────────┴─────────┘
```

---

## Adding Google Calendar / Gmail API later

When you're ready to upgrade from Gmail IMAP to the full Google API:
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable Gmail API + Calendar API
3. Create OAuth credentials → download `credentials.json`
4. Replace the IMAP tools in `agent/tools.py` with the Google API client

This is completely optional — IMAP works well for personal use.
