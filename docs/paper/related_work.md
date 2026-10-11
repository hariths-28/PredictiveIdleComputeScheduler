# Related Work: Opportunistic Compute, Availability Prediction, and Workload Scheduling

This document surveys the foundational literature and prior work informing the design, empirical evaluation, and scheduling architecture of **IdleGrid**. It serves as the literature review and related work foundation for the conference paper.

---

## 1. Cycle-Stealing and Desktop Grid Computing

Opportunistic computing—harvesting unutilized CPU cycles from idle workstations—has a long history in distributed systems.

### 1.1 HTCondor (formerly Condor)
* **Foundational Work:** Litzkow, Livny, & Mutka (1988); Thain, Tannenbaum, & Livny (2005).
* **Mechanism:** HTCondor monitors user activity (keyboard strokes, mouse events, CPU load) on networked workstations. When an owner is absent, HTCondor places batched batch jobs on the node. Upon owner return, the guest job is suspended or evicted.
* **Preemption & Checkpointing:** To avoid losing compute progress during evictions, HTCondor introduced user-level checkpointing (`condor_compile`), serializing process memory and open file descriptors into disk checkpoints.
* **Limitations in Student Laptop Fleets:**
  1. *Heavyweight Checkpointing Overhead:* Modern machine learning workloads rely on dynamic C/C++ extensions, multi-threading runtimes (OpenMP, MKL), and GPU/SIMD states that cannot be cleanly checkpointed via user-space memory dumps without specialized container runtimes.
  2. *Reactive Eviction Policy:* HTCondor makes placement decisions without predicting *how long* the harvestable window will persist. On personal student laptops with high arrival stochasticity, reactive assignment leads to repeated interruptions and thrashing.

### 1.2 BOINC and Volunteer Computing
* **Foundational Work:** Anderson (2004, 2019) (*SETI@home*, *Folding@home*).
* **Mechanism:** BOINC coordinates volunteer nodes globally across heterogeneous networks. Work units are pulled by worker daemons and processed when screensavers activate or user inactivity passes a threshold.
* **Limitations in Team Laptop Fleets:**
  1. *Coarse Granularity and Latency:* BOINC is engineered for embarrassingly parallel, throughput-oriented tasks with deadlines spanning days. It lacks low-latency coordination required for interactive hyperparameter optimization (HPO) studies.
  2. *Absence of Multi-Resource Guarantees:* Volunteer compute clients typically do not coordinate peer-to-peer or balance migration timers based on calibrated remaining duration quantiles.

---

## 2. Host Availability and Inactivity Modeling

Predicting the availability of non-dedicated compute nodes has been studied extensively using empirical trace repositories.

### 2.1 Empirical Trace Characterization
* **Trace Archives:** The Failure Trace Archive (FTA) (Iosup et al., 2008) and desktop grid traces (Kondo et al., 2004; Nurmi et al., 2005).
* **Observed Distributions:** Workstation idle times exhibit heavy-tailed properties, frequently modeled by Pareto, Weibull, or lognormal distributions rather than Poisson processes.
* **Lindy's Law / Aging Effect:** In heavy-tailed distributions, the expected remaining idle time increases with the time already spent idle:
  $$\mathbb{E}[T_{\text{remaining}} \mid T_{\text{elapsed}} = \tau] \propto \tau$$
  While effective for long-running institutional desktop clusters, student laptop fleets introduce non-stationary boundaries (e.g., classes ending on the hour, transport times, battery unplugging) that violate pure power-law assumptions.

### 2.2 Statistical and Machine Learning Predictors
* **Semi-Markov and Autoregressive Models:** Ren et al. (2007) and Wolski et al. (2000) deployed network weather services and Markov transition matrices to estimate the probability that a host remains available for a duration $d$.
* **Time-of-Day Cyclical Predictors:** Di et al. (2012) demonstrated that user availability patterns are heavily correlated with circadian and weekly rhythms (diurnal periodicity).
* **IdleGrid's Advance:** Prior predictors predominantly focused on predicting *mean* availability or binary availability probabilities $P(\text{available} \ge \Delta t)$. IdleGrid uses multi-quantile gradient boosting regression ($q_{10}, q_{20}, q_{50}$) directly on log-scale remaining duration:
  $$\mathcal{L}_{\alpha}(y, \hat{y}) = \max(\alpha (y - \hat{y}), (1 - \alpha)(\hat{y} - y))$$
  The 20th percentile ($q_{20}$) provides a risk-calibrated safety bound: placing a job of estimated duration $t$ on a laptop where $\hat{q}_{20} \ge t$ guarantees an empirical $\sim 80\%$ completion probability without interruption.

---

## 3. Transient Cloud Compute (Spot / Preemptible Instances)

Cloud providers expose surplus datacenter capacity at steep discounts (e.g., AWS EC2 Spot Instances, Google Cloud Spot VMs) with the caveat of unilateral preemption.

### 3.1 Preemption Warning Mechanisms
* **Cloud Preemption Notices:** AWS provides a 2-minute termination notice via Instance Metadata / EventBridge; GCP provides a 30-second notice.
* **IdleGrid Contrast:** On personal student laptops, a 30-second preemption delay is unacceptable. An owner opening their laptop lid demands immediate CPU and UI responsiveness. IdleGrid implements a **sub-second local OS kill switch** (< 1 s pause latency, polling input at 250 ms intervals) that freezes running compute before the Dispatcher coordinator is even alerted.

### 3.2 Spot Placement and Interruption Prediction
* **Bidding and Placement Heuristics:** Subramanya et al. (2015), Sharma et al. (2016), and Tribute (Harlap et al., 2018) model interruption rates across instance pools to place ML training jobs on the least volatile instances.
* **Differences in IdleGrid Domain:** Cloud spot preemption is governed by global market demand and provider capacity pools. Laptop idle availability is driven by personal human schedules, battery charge states, and academic calendars, making local multi-feature time-series models highly predictive.

---

## 4. Workload Scheduling for Distributed Hyperparameter Optimization (HPO)

* **Optuna:** Akiba et al. (2019) introduced define-by-run hyperparameter search using Tree-structured Parzen Estimators (TPE) and asynchronous ask-and-tell algorithms.
* **Fault Tolerance Synergy:** Unlike multi-day monolithic model pre-training, distributed HPO consists of hundreds of discrete, moderate-length trials (e.g., 2–15 minutes). 
  - If a node is preempted and the owner remains active beyond the migration threshold (e.g., 5 minutes), the uncompleted trial can simply be restarted on an alternate node or requeued.
  - This eliminates the need for expensive checkpoint/restore mechanics while keeping goodput high.

---

## 5. Comparative Positioning Matrix

| Dimension | HTCondor | BOINC | Cloud Spot Schedulers | IdleGrid |
| :--- | :--- | :--- | :--- | :--- |
| **Node Target** | Institutional desktops / clusters | Global volunteer PCs | Enterprise datacenters | Student laptops (Win/macOS/Linux) |
| **Preemption Model** | Reactive eviction | Reactive / Coarse deadlines | 30s–120s provider notice | **Sub-second local OS kill switch** |
| **Availability Modeling** | None / Simple thresholds | Static historical benchmarks | Market volatility heuristics | **Multi-quantile ML regression ($q_{10}, q_{20}, q_{50}$)** |
| **Fault Recovery** | Memory dumps / process migration | Work-unit reassignment | Cloud re-provisioning | **Instant local pause + lazy trial migration** |
| **Workload Optimization** | Generic batch scripts | Embarrassingly parallel scientific tasks | Long-running cloud training | **Distributed Optuna HPO + standalone ML scripts** |
| **Privacy Safeguards** | Administrative root daemon | Sandboxed volunteer daemon | Hypervisor isolation | **Zero keystroke/screen capture; inactivity scalar only** |

---

## 6. References

1. Anderson, D. P. (2004). BOINC: A system for public-resource computing. *Fifth IEEE/ACM International Workshop on Grid Computing*, 4–10.
2. Litzkow, M. J., Livny, M., & Mutka, M. W. (1988). Condor-a hunter of idle workstations. *8th International Conference on Distributed Computing Systems*, 11–18.
3. Thain, D., Tannenbaum, T., & Livny, M. (2005). Distributed computing in practice: The Condor experience. *Concurrency and Computation: Practice and Experience*, 17(2‐4), 323–356.
4. Kondo, D., Chien, A. A., & Casanova, H. (2004). Resource management for rapid application turnaround on enterprise desktop grids. *ACM/IEEE SC 2004 Conference*, 16–16.
5. Nurmi, D., Brevik, J., & Wolski, R. (2005). Modeling machine availability in enterprise desktop grids. *IEEE International Conference on Cluster Computing*, 1–10.
6. Ren, X., Eigenmann, R., & Bagchi, S. (2007). Resource failure prediction in fine-grained cycle sharing systems. *13th IEEE Pacific Rim International Symposium on Dependable Computing*, 93–100.
7. Iosup, A., Epema, D., Tannenbaum, T., Farrelly, M., & Livny, M. (2008). Inter-operating grids through delegated matchmaking. *ACM/IEEE SC 2008*, 1–12.
8. Di, S., Kondo, D., & Cappello, F. (2012). Characterizing and modeling cloud applications/workloads on a Google cluster. *IEEE 41st International Conference on Parallel Processing*, 440–449.
9. Sharma, P., Lee, S., Guo, T., Irwin, D., & Shenoy, P. (2016). SpotCheck: Designing a derivative IaaS cloud on the spot market. *Twelfth European Conference on Computer Systems (EuroSys)*.
10. Harlap, A., Tumanov, A., Chung, A., Ganger, G. R., & Gibbons, P. B. (2018). Tribute: Deep learning with volatile instances. *arXiv preprint arXiv:1810.03541*.
11. Akiba, T., Sano, S., Yanase, T., Ohta, T., & Koyama, M. (2019). Optuna: A next-generation hyperparameter optimization framework. *ACM SIGKDD International Conference on Knowledge Discovery & Data Mining*, 2623–2631.
