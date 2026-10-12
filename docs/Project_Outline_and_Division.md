# Project Charter: Predictive Idle-Compute Scheduler for ML Workloads

## 1\. Project Overview

**Project Title:** Predictive Idle-Compute Scheduler for ML Workloads
*(Alternative/Catchy Names: ComputeShare, IdleNode, ML-Grid)*

**The Problem:** University CS departments and student groups waste massive amounts of compute power. Lab computers and personal laptops sit completely idle while students simultaneously hit compute limits on platforms like Google Colab when trying to train Machine Learning models.

**The Objective:** To build a distributed compute-sharing platform for local networks (like a team's shared Wi-Fi). The system will monitor a network of laptops, detect when a machine is completely idle, and automatically route incoming heavy scripts (like ML training jobs) to that idle machine without interrupting the actual owner's work.

**The Outcome (10-Day MVP):** A functional "walking skeleton" demonstrated across a local network of team laptops. The final demo will consist of two parts:

1. **Live Routing:** A terminal-based system that successfully detects an idle laptop, sends a dummy payload (e.g., a heavy math script) to it, executes it, and returns the result.
2. **Predictive Proof-of-Concept:** A Jupyter Notebook demonstrating a Scikit-Learn machine learning model trained on the team's actual usage data, capable of predicting *how long* a machine will stay idle based on the time of day and day of the week.

\---

## 2\. Team Workload Distribution (5 Members)

To successfully build this as a team of beginners, the architecture is split into 5 distinct, decoupled domains. Every member owns their specific piece of the puzzle and acts as the "API" for the rest of the team.

### Role 1: The Node Agent (The "Spy")

* **Objective:** Monitor the hardware and user activity of the host laptop.
* **Responsibilities:** Write a lightweight Python script that runs in the background of all team laptops. It must check CPU usage, RAM usage, and monitor for mouse/keyboard activity to determine if the user is present.
* **Crucial Feature:** The "Kill Switch." If a borrowed machine suddenly wakes up (the owner wiggles the mouse), the Agent must immediately kill/pause the background compute job to prevent lagging the owner's laptop.
* **Tech Stack:** Python, `psutil` (hardware stats), `pynput` (mouse/keyboard detection).

### Role 2: The Dispatcher (The "Traffic Cop")

* **Objective:** Act as the central brain that matches idle laptops with incoming jobs.
* **Responsibilities:** Build a central API server. It does *not* execute the code or store long-term memory; it just listens to the network. When it receives a "status update" from a Node Agent, it notes it. When a user submits a script to be run, the Dispatcher finds the best idle machine and routes the job there.
* **Tech Stack:** Python, Flask or FastAPI, HTTP/REST network requests.

### Role 3: The State Manager (The "Record Keeper")

* **Objective:** Design and maintain the memory of the system.
* **Responsibilities:** Build the database that tracks everything. The Dispatcher (Role 2) will constantly ask the State Manager to save and retrieve data. You will track: which laptops are online, what their current load is, the queue of pending jobs, and the historical logs of when laptops were idle vs. busy.
* **Tech Stack:** MySQL, MySQL Workbench, relational database design, Python SQL connectors.

### Role 4: The ML Oracle (The "Fortune Teller")

* **Objective:** Move the system from "Naive" (reacting to current idle status) to "Predictive" (guessing future idle time).
* **Responsibilities:** Have the team run the Node Agent for a few days to harvest CSV logs of their laptop usage. Take this raw data (Time of Day, Day of Week, Idle Duration) and train a Machine Learning model. The goal is to predict if a laptop will be idle long enough to finish a specific job.
* **Tech Stack:** Python, Pandas (data cleaning), Scikit-Learn (Decision Trees, Logistic Regression).

### Role 5: The Executor \& UI (The "Delivery Driver \& Customer App")

* **Objective:** Handle the physical packaging, moving, and running of the scripts.
* **Responsibilities:**

  1. **The UI:** Build a simple Command Line Interface (CLI) so a user can type `submit\_job my\_script.py`.
  2. **The Delivery:** Write the code that zips the script, sends it to the Dispatcher, unzips it on the target idle machine, securely runs it in the terminal (`python3 my\_script.py`), grabs the output file (e.g., `results.csv`), and sends it back to the original user.
* **Tech Stack:** Python (`requests`, `argparse`/`click`), Linux/Ubuntu terminal commands (`chmod`, system processes), File I/O operations.

\---



Role 1: Arya

Role 2: Harith

Role 3: Amaan

Role 4: Rejish

Role 5: Ronith

## 

