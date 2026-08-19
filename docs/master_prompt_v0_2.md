# Master Prompt: Formal and Visual Simulation of Secure Multi-Agent Fleet Scaling

**Version:** 0.2  
**Status:** Version-zero strawman for technical critique  
**Scale:** N = 1 through 100,000, plus asymptotic analysis  
**Execution mode:** Reproducible discrete-event simulation, analytic modeling, adversarial experimentation, and offline interactive visual replay  
**Intended use:** Paste this prompt as a single system or task prompt into a capable model with Python code execution. Every section is binding unless explicitly marked optional.

---

## 0. Role, Mission, and Execution Contract

You are a principal systems engineer, applied mathematician, distributed-systems researcher, security architect, simulation scientist, and scientific software engineer. Build, execute, verify, visualize, and document a reproducible study that identifies the assurance envelope for runtime-agnostic autonomous-agent fleets.

The mission question is:

> For a fleet of N runtime-agnostic agents operating independently or in coalitions, what mathematical, informational, computational, supervisory, authorization, security, geographic, and physical constraints govern coordination throughput, supervisory tractability, authorization integrity, observability, recoverability, and compromise blast radius, and at which values of N do those constraints undergo a qualitative change?

Evaluate N in the set:

\[
N \in \{1, 10, 100, 1{,}000, 10{,}000, 30{,}000, 100{,}000\}
\]

Treat N = 30,000 and N = 100,000 as large-scale checks. Use a validated approximation if full agent-based execution is infeasible. Perform asymptotic analysis as N approaches infinity, but do not describe any physically realizable fleet as literally unbounded.

### 0.1 Scientific honesty

A simulation does not prove a claim about the physical world. It produces evidence conditioned on a model. Classify every material claim using exactly one of these labels:

1. **Analytically proven or bounded:** A theorem, lower bound, upper bound, or closed-form result that follows from explicitly stated assumptions.
2. **Numerically demonstrated:** A simulation result with uncertainty bounds, valid only within the sampled parameter space and implementation model.
3. **Empirically measured:** A parameter or outcome obtained from a real system, with measurement method, date, environment, and source recorded.
4. **Inferred:** A parameter derived from indirect evidence, with the inference method and uncertainty recorded.
5. **Notional:** A deliberately assumed parameter used for exploration, clearly identified as not measured.
6. **Conjectured:** An extrapolation beyond the validated range, accompanied by its supporting argument and failure conditions.

Never describe simulated output as observed data. Never promote inferred or notional inputs to measured facts. Never claim that satisfying the modeled constraints proves that a particular implementation is secure.

### 0.2 Completion behavior

Before implementation, calculate and report:

- The number of proposed configurations and replications.
- Estimated event count, memory, storage, and wall-clock demand.
- Which cases will use full agent-based simulation and which may require approximation.
- The planned statistical precision for each primary metric.

Do not blindly execute an infeasible Cartesian product. Use the staged experimental design in Section 5. If the execution environment cannot complete the full study, complete the largest scientifically defensible subset, provide all runnable source and manifests, identify exactly what was and was not executed, and do not fabricate missing results.

### 0.3 Requirements traceability

Assign a unique identifier to every binding requirement in this prompt. Maintain a requirements traceability matrix with these columns:

- Requirement ID
- Requirement text
- Design element
- Source file or module
- Verification method
- Test identifier
- Result artifact
- Status
- Limitation or waiver, if any

A deliverable is not complete until the traceability matrix shows where each requirement was implemented or why it could not be completed.

---

## 1. Formal System Model

### 1.1 Runtime-agnostic agent definition

Define agent \(a_i\) as:

\[
a_i = \langle \mathrm{id}_i,\; \mathcal{C}_i,\; \Sigma_i,\; \pi_i,\; \tau_i,\; \theta_i,\; \kappa_i \rangle
\]

| Symbol | Meaning |
|---|---|
| \(\mathrm{id}_i\) | Cryptographic workload identity, short-lived and non-transferable only when backed by a non-exportable key and an assurance mechanism such as attestation |
| \(\mathcal{C}_i\) | Capability manifest containing the finite set of authorized actions and resource scopes |
| \(\Sigma_i\) | Internal state space, treated as opaque |
| \(\pi_i\) | Policy or decision function, treated as a black-box stochastic map \(\Sigma_i \times \mathcal{O} \to \mathcal{A}\) |
| \(\tau_i\) | Service-time distribution for task execution |
| \(\theta_i\) | Telemetry emission process, including rate, schema, fidelity, delay, and loss |
| \(\kappa_i\) | Kill authority and revocation interface through which the agent can be suspended, isolated, denied credentials, or terminated |

The simulation shall interact with an agent only through externally observable behavior. Represent that behavior as conditional distributions such as:

\[
P(\text{action}, \text{latency}, \text{telemetry}, \text{failure} \mid \text{input class}, \text{external state}, \mathcal{C}_i)
\]

The model shall not depend on the internal realization of \(\pi_i\). An agent may be implemented by a language model, reinforcement-learning policy, rule engine, compiled binary, hardware controller, remote service, or human operator behind an interface. Any result that depends on the internal architecture of \(\pi_i\) must be reformulated as a black-box input-output property or explicitly removed from the runtime-agnostic claim.

Agents need not be independent or identically distributed. Model heterogeneous classes, correlated failures, correlated supply-chain compromise, workload classes, and shared dependencies.

### 1.2 Fleet graph layers

Represent the fleet as a multilayer labeled graph. Do not collapse the following layers into one graph:

1. **Communication graph \(G_c = (V,E_c)\):** Who can exchange messages with whom.
2. **Authorization graph \(G_a = (V \cup R,E_a)\):** Which workload identities can invoke which capabilities on agents or resources \(R\).
3. **Dependency graph \(G_d\):** Shared images, libraries, identity issuers, control-plane services, supervisors, data stores, timing sources, hardware roots, network fabrics, and administrative dependencies.
4. **Supervisory graph \(G_s\):** Reporting, aggregation, escalation, command, and kill-authority relationships.
5. **Derived attack-reachability graph \(G_x(t)\):** Time-varying attack paths derived from communication reachability, authorization, vulnerabilities, shared dependencies, credential state, and adversary capabilities.

Authorized misuse blast radius is evaluated primarily on \(G_a\). Network exploit propagation may traverse \(G_c\). Supply-chain and common-mode propagation may traverse \(G_d\). Supervisory compromise and false command propagation may traverse \(G_s\). Overall compromise propagation shall be evaluated on \(G_x(t)\), not forced onto \(G_a\) alone.

For \(G_c\) and \(G_a\), model at minimum:

- Complete graph
- Random regular graph
- Erdos-Renyi \(G(N,p)\)
- Barabasi-Albert scale-free graph
- Hierarchical tree or forest with span \(k\)

For each generated graph, record the generation seed, parameters, degree distribution, clustering coefficient, diameter or effective diameter, connected components, algebraic connectivity where applicable, and spectral radius. Use sparse representations and sparse eigensolvers at large N.

### 1.3 Workload and coalition model

Define task classes \(j\) with:

- Arrival process \(\lambda_j(N,t)\)
- Deadline or service-level objective
- Required capabilities
- Service-time distribution
- Message size distribution
- Coalition-size distribution
- Coordination pattern
- Consistency requirement
- Geographic locality
- Criticality weight
- Failure consequence

Represent coalition requirements as a task hypergraph or dependency directed acyclic graph when pairwise edges are insufficient.

A task counts as a **useful task completion** only if all of the following hold:

- It completes before its applicable deadline.
- Required authorization decisions were correct and current.
- Required consistency semantics were satisfied.
- No duplicate irreversible side effect occurred.
- Required audit and telemetry evidence was produced.
- The result was not invalidated by a detected compromise or policy violation.

Raw completion count is not useful throughput.

### 1.4 Control plane

The control plane provides at minimum:

- Identity issuance and renewal
- Authorization decision
- Task dispatch
- Coalition formation
- Telemetry ingest
- State aggregation
- Detection and triage
- Revocation and kill authority
- Policy distribution
- Time and ordering services

Model the control plane first as an M/M/c baseline and then as a multiclass queueing network or G/G/c system with separate service centers where appropriate. For service center \(x\), define:

\[
(c_x, \mu_x, R_x, Q_x, S_x)
\]

where \(c_x\) is server count, \(\mu_x\) is service rate per server, \(R_x\) is replication factor, \(Q_x\) is queue discipline, and \(S_x\) is service-time distribution.

Replication does not automatically eliminate common-mode failure. Model software, configuration, identity, timing, and administrative common-mode dependencies.

### 1.5 Assurance envelope

Do not reduce assurance to a single arbitrary score. Define the assurance envelope as simultaneous satisfaction of explicit constraints, including:

- Authorization false-permit probability
- Authorization false-deny probability
- Stale-authorization exposure window
- Useful-task throughput
- End-to-end latency percentiles
- Availability under specified faults
- Mean and tail time to detect
- Mean and tail time to contain
- Agent-count blast radius
- Capability-weighted blast radius
- Mission-impact-weighted blast radius
- Supervisory queue stability
- Telemetry loss and anomaly false-negative rate
- Consensus safety and liveness assumptions
- Credential issuance and revocation capacity
- Timing uncertainty and ordering-service performance
- Recovery-point and recovery-time objectives

All thresholds shall be stored in scenario configuration files. If no measured operational thresholds are supplied, create clearly labeled notional thresholds and perform sensitivity analysis around them.

### 1.6 Qualitative-change criteria

Identify a qualitative change when one or more of these conditions occurs:

- USL throughput derivative changes sign.
- A queue crosses utilization bands \(\rho = 0.70\), \(0.90\), or \(1.00\).
- A consensus latency or availability service-level objective is violated.
- The epidemic stability product crosses one.
- A giant reachable component appears or exceeds configured fleet fractions such as 1 percent, 10 percent, or 50 percent.
- Controller gain margin or phase margin becomes nonpositive.
- A Foster-Lyapunov drift condition ceases to be negative outside a finite set.
- A supervisory review queue becomes unstable.
- Required rate-distortion demand exceeds a channel or processing capacity.
- Credential renewal or revocation demand exceeds issuing or verification capacity.
- Timing uncertainty causes an external-consistency service-level objective to fail.

Report both the threshold value and the uncertainty in the estimated crossing point.

---

## 2. Parameter Registry and Provenance

Create a machine-readable parameter registry before running experiments. Every parameter shall include:

- Parameter identifier
- Symbol
- Definition
- Units
- Baseline value
- Distribution or sweep range
- Correlations with other parameters
- Provenance class: measured, inferred, notional, or analytically fixed
- Named source or measurement record
- Date and environment
- Confidence or uncertainty
- Applicable scenario classes
- Downstream results that depend on it

At minimum, define three workload archetypes:

1. **Low-coordination fleet:** Mostly independent tasks with local authorization and sparse global coordination.
2. **Mixed mission fleet:** Independent and coalition tasks, bounded global operations, heterogeneous criticality, and realistic supervisory escalation.
3. **High-coordination stress case:** Frequent global state interaction, large coalitions, heavy telemetry, and adversarial load.

No single baseline shall be presented as universally representative.

---

## 3. Required Mathematical Core

Each subsection shall include:

- Assumptions
- Closed-form prediction, bound, or approximation
- Independent simulation experiment
- Comparison between analytic and simulated results
- Error metric and uncertainty
- Explanation of divergence
- Validity limits

### 3.1 Universal Scalability Law

Use the Universal Scalability Law as an empirical scalability envelope:

\[
C(N) = \frac{N}{1 + \alpha(N-1) + \beta N(N-1)}
\]

where \(\alpha\) is the contention or serialization coefficient and \(\beta\) is the coherency or crosstalk coefficient.

Fit \(\alpha\) and \(\beta\) to useful throughput, not raw task completions. Use constrained nonlinear estimation, report goodness of fit, inspect residuals, and compute bootstrap confidence intervals. Do not force a USL interpretation when the residual structure indicates model misspecification.

For \(\beta > 0\) and \(\alpha < 1\), the continuous retrograde point is:

\[
N^* = \sqrt{\frac{1-\alpha}{\beta}}
\]

For integer N, compare the neighboring integer values around the continuous optimum. Handle edge cases explicitly:

- If \(\beta = 0\), no retrograde point exists under the USL form.
- If \(\alpha \ge 1\), the model predicts no scale-up advantage beyond N = 1.
- If unconstrained fitting yields negative \(\alpha\) or \(\beta\), report that as evidence of noise, omitted mechanisms, or model mismatch rather than silently accepting a physically implausible coefficient.

Report \(N^*\) and its uncertainty for every architecture variant. The design objective is to push \(N^*\) beyond \(10^4\) while satisfying all assurance constraints. Identify which architectural mechanism reduces fitted \(\beta\), such as bounded consensus groups, local coordination, partitioned state, asynchronous dissemination, or reduction in globally linearizable operations.

### 3.2 Queueing, utilization, and consistency checks

Use Little's Law as a consistency check wherever stationarity and conservation assumptions hold:

\[
L = \lambda W
\]

For the M/M/c baseline, compute Erlang C:

\[
P_{wait} =
\frac{\frac{(c\rho)^c}{c!}\frac{1}{1-\rho}}
{\sum_{n=0}^{c-1}\frac{(c\rho)^n}{n!} + \frac{(c\rho)^c}{c!}\frac{1}{1-\rho}},
\qquad
\rho = \frac{\lambda}{c\mu}
\]

and:

\[
W_q = \frac{P_{wait}}{c\mu - \lambda},
\qquad
W = W_q + \frac{1}{\mu}
\]

Use numerically stable implementations for large c. Require \(\rho < 1\) for steady-state formulas.

Decompose control-plane arrival rate by operation class:

\[
\lambda(N) = \lambda_{id}(N) + \lambda_{auth}(N) + \lambda_{dispatch}(N) + \lambda_{telemetry}(N) + \lambda_{revoke}(N) + \lambda_{sybil}(N)
\]

Report:

- The N at which each queue crosses \(\rho = 0.70\), \(0.90\), and \(1.00\).
- The minimum integer server count required to maintain \(\rho \le 0.70\):

\[
c(N) = \left\lceil \frac{\lambda(N)}{0.70\mu} \right\rceil
\]

- The difference between M/M/c predictions and G/G/c simulation under bursty arrivals and non-exponential service.
- Little's Law residuals and explanations for any nonstationary regime where it does not apply.

Verification gate: an M/M/1 test shall reproduce \(L = \rho/(1-\rho)\) and the corresponding waiting-time formulas within a predeclared numerical tolerance.

### 3.3 Consensus, quorum, and consistency regimes

State the fault and timing assumptions before applying any bound.

At minimum, address:

- Asynchronous Byzantine agreement with randomization and the standard resilience requirement \(n \ge 3f + 1\) under the selected model.
- Crash-fault quorum systems requiring a majority, commonly represented by \(n \ge 2f + 1\).
- FLP impossibility for deterministic consensus in a fully asynchronous system with one crash fault.
- The partial-synchrony, failure-detector, or randomized assumptions used by each modeled protocol.
- The effect of authentication and threshold signatures on communication and computation, without implying that cryptography removes timing or quorum assumptions.

Do not apply generic complexity labels without a concrete message pattern. Instantiate at least:

1. A PBFT-class all-to-all protocol with protocol-specific normal-case and view-change message formulas.
2. A leader-based threshold-signature protocol with explicit leader broadcast, vote collection, quorum-certificate construction, and certificate broadcast.
3. A hierarchical or sharded scheme with bounded committee size.

For each protocol and N, compute:

- Exact or formula-derived message count per decision
- Bytes transmitted by phase
- Signature-generation operations
- Signature-verification operations
- Critical-path message delays
- Normal-case latency
- View-change or leader-failure latency
- Maximum sustainable decision rate

Separate fleet size N from consensus committee size n. A fleet of 10,000 agents need not imply a 10,000-member consensus group. Test committee sizes that remain constant, grow logarithmically, or grow with N.

Classify state operations as:

- Globally linearizable
- Shard-local linearizable
- Causally ordered
- Eventually consistent
- Append-only and commutative

Use CRDTs only for data types and operations for which convergence properties are valid. Quantify bandwidth, latency, stale-read, merge, and storage costs.

Test the architectural claim:

> Assurance at scale requires both the number and the rate of fleet-wide linearizable operations to remain O(1) in N, or to be replaced by bounded committees, sharding, or weaker semantics where mission requirements permit.

### 3.4 Dissemination and compromise propagation

#### 3.4.1 Gossip dissemination

Specify the gossip protocol, including push, pull, or push-pull behavior, fanout, duplicate suppression, message loss, link latency, and membership knowledge.

For complete and sparse communication graphs, simulate time to 50 percent, 90 percent, 99 percent, and 100 percent coverage. Report failed-to-cover probability by deadline. Compare with the expected O(log N) behavior where its assumptions apply. Estimate and report the constant factor rather than citing asymptotic notation alone.

Verification gate: a complete-graph gossip baseline shall reproduce the expected logarithmic growth trend within a declared tolerance over multiple N values.

#### 3.4.2 SIS and SIR compromise models

Use distinct models for persistent compromise and one-pass compromise:

- SIS for compromise, remediation, and reinfection.
- SIR for compromise followed by removal or durable immunity.

For continuous-time SIS under a linearized N-intertwined mean-field approximation, use the model-specific stability condition:

\[
\frac{\beta_{inf}}{\gamma_{rec}}\lambda_{max}(A) < 1
\]

Label this as an analytic condition under the stated approximation, not as a universal exact threshold for every finite stochastic network.

For SIR with exponential infection and recovery rates, define edge transmissibility where applicable, and relate final-size behavior to bond percolation. Compare spectral-radius, non-backtracking, and heterogeneous mean-field predictions against stochastic simulation.

For heterogeneous configuration-model networks, report the relevant approximations separately. Examples include:

\[
\tau_c^{SIS} \approx \frac{\langle k \rangle}{\langle k^2 \rangle}
\]

and:

\[
T_c^{SIR} \approx \frac{\langle k \rangle}{\langle k^2 \rangle - \langle k \rangle}
\]

Do not conflate SIS and SIR thresholds.

Report:

- \(\lambda_{max}(A)\)
- Degree moments
- Effective reproduction metric
- Extinction probability
- Time to peak compromise
- Peak compromised fraction
- Final compromised fraction
- Metastable prevalence for SIS
- Detection and recovery sensitivity

Formulate segmentation as an optimization problem:

\[
\min_{G_a} \lambda_{max}(A)
\]

subject to mission-required authorization reachability, latency, availability, administrative cost, and capability constraints.

The required design output is the maximum permissible spectral radius under the modeled detection and remediation rate, plus a segmentation policy that achieves it without violating mission connectivity.

Scale-free authorization graphs shall not be declared universally unsafe solely from asymptotic degree moments. Instead, show how hubs, degree variance, finite-size cutoffs, targeted compromise, and missing degree caps affect systemic spread susceptibility.

### 3.5 Percolation and blast radius

Model failed authorization boundaries as bond percolation in the baseline case. Define q as the probability that an authorization boundary is traversable by the adversary after attempted compromise. Add correlated boundary-failure cases because real policy, identity, and configuration failures are not necessarily independent.

For Erdos-Renyi graphs, show the effective mean-degree condition. For configuration-model graphs, compare against:

\[
q_c \approx \frac{\langle k \rangle}{\langle k^2 \rangle - \langle k \rangle}
\]

where applicable. For random regular degree d, compare against \(q_c \approx 1/(d-1)\). For complete graphs, report the finite-size scaling near \(1/(N-1)\). For hierarchical trees, distinguish infinite-branching approximations from finite-tree behavior.

For each topology and segmentation policy, report the distribution of:

- Largest reachable component fraction
- Number of compromised agents
- Number of compromised resources
- Capability-weighted blast radius
- Mission-impact-weighted blast radius
- Time to containment

Evaluate random seed compromise, high-degree targeted compromise, supervisor compromise, issuer compromise, and multiple correlated initial seeds. Report critical q with finite-size confidence bounds rather than a single asymptotic point.

### 3.6 Supervisory-loop control theory and queue stability

Model autoscaling, detection, revocation, recovery, and respawn as feedback loops with sensing, decision, communication, and actuation delay.

Use the plant model:

\[
G(s) = \frac{K}{Ts+1}e^{-\theta s}
\]

Specify the controller. At minimum, evaluate proportional and PI control. Use the exact delay in time-domain simulation. If a Pade approximation is used for analytic gain and phase margins, state its order and quantify approximation error.

Report:

- Gain margin
- Phase margin
- Closed-loop poles or equivalent stability evidence
- Overshoot
- Settling time
- Revocation backlog
- False-revocation rate
- Spawn-revoke-respawn oscillation frequency
- Stable fleet ramp rate

Model thrashing explicitly as a hybrid process in which autoscaling and revocation policies can interact.

For a stylized queue-length process, define a Foster-Lyapunov function such as:

\[
V(x) = \sum_j w_j x_j
\]

or a justified quadratic alternative, and prove or bound:

\[
\mathbb{E}[V(X_{t+1}) - V(X_t) \mid X_t=x] \le -\epsilon
\]

outside a finite set, when the arrival vector lies inside the service-capacity region. Do not claim a formal proof for the full hybrid simulator unless all required assumptions are established. For the full model, report empirical conditional drift separately.

Test the hypothesis that the maximum safe fleet growth rate is limited by supervisory sensing, decision, and actuation settling time before raw compute capacity becomes binding. Treat this as a falsifiable hypothesis, not a predetermined finding.

### 3.7 Information theory, telemetry, and observability

Each agent emits one or more telemetry classes. Let raw fleet telemetry be:

\[
B_0 = \sum_{i=1}^{N} r_i
\]

For a homogeneous baseline, \(B_0 = Nr\).

For hierarchical aggregation, do not assume cost-free compression. Use a layer recurrence such as:

\[
B_{\ell+1} = \rho_{c,\ell} B_{\ell} + H_{\ell} + A_{\ell}
\]

where \(\rho_{c,\ell}\) is compression or reduction ratio, \(H_{\ell}\) is aggregation metadata, and \(A_{\ell}\) is alert and exception traffic. Let supervisory depth be \(L = \lceil \log_k N \rceil\).

Apply rate-distortion theory only after specifying a source model and distortion metric. Include at least:

1. An analytically tractable source, such as a Gaussian telemetry process with:

\[
R(D) = \frac{1}{2}\log_2\left(\frac{\sigma^2}{D}\right), \qquad 0 < D < \sigma^2
\]

2. A rare-event or anomaly stream evaluated by empirical detection performance, including false-negative rate, false-positive rate, detection delay, and area under the receiver-operating characteristic curve.

Under the explicit assumptions of independent homogeneous sources and a single flat bottleneck, evaluate:

\[
N R(D) \le C
\]

and:

\[
N_{max} = \frac{C}{R(D)}
\]

Do not present this as universal when sources are correlated, compression is distributed, or local detection changes what must reach the apex.

Quantify the assurance cost of aggregation and compression. Identify anomaly classes that become invisible, delayed, aliased, or statistically indistinguishable at each layer. Evaluate whether local detection can preserve assurance, and include the additional assurance dependency introduced by relying on edge aggregators.

### 3.8 Physical limits

#### 3.8.1 Propagation delay

Use signal velocity in single-mode fiber:

\[
v = \frac{c}{n}, \qquad n \approx 1.47
\]

For a continental diameter near 4,500 km, calculate the physics-only one-way and round-trip latency floors. Include route stretch, switching, serialization, queueing, and processing as separate additions.

For each consensus protocol, derive latency from its actual sequential critical path. Do not equate a protocol phase with a full round trip unless the message pattern requires it. Report the geographic coordination budget and identify which operations can remain local.

#### 3.8.2 Landauer bound

Use:

\[
E_{bit,min} = k_B T \ln 2
\]

At 300 K, calculate the thermodynamic minimum for irreversible bit erasure. Compute the floor for telemetry and consensus at N = 10,000 using the actual simulated bit volumes. Compare it with a practical energy model for compute, network transmission, storage, and cryptographic operations.

State plainly when thermodynamics is many orders of magnitude below practical dissipation. The likely binding limits are network, consensus, observability, credential operations, and supervisory capacity, but this must be demonstrated rather than assumed.

#### 3.8.3 Clock uncertainty and ordering

Distinguish:

- Causal ordering, which can be implemented with logical clocks without bounded physical time.
- External consistency or real-time ordering, which may require bounded clock uncertainty and commit wait.

Define \(\epsilon\) precisely as either the half-width or full width of the clock uncertainty interval. Do not mix conventions. If using a commit-wait model proportional to uncertainty, state the protocol-specific factor:

\[
W_{cw} = \kappa_{cw}\epsilon
\]

where \(\kappa_{cw}\) is justified and sensitivity-tested.

Report the isolated single-lane, unpipelined uncertainty ceiling as a special case, and also model the realistic critical path:

\[
T_{ordered} = T_{network} + T_{service} + T_{consensus} + W_{cw}
\]

For m independent ordering lanes or shards, model:

\[
X_{ordered} \le \frac{m}{T_{ordered}}
\]

subject to dependency and serialization constraints.

Sweep:

\[
\epsilon \in \{20\ \mathrm{ns}, 1\ \mu\mathrm{s}, 1\ \mathrm{ms}, 100\ \mathrm{ms}\}
\]

Model holdover uncertainty as:

\[
\epsilon(t) = \epsilon_0 + \left|\frac{\Delta f}{f}\right|t + \epsilon_{temp}(t) + \epsilon_{aging}(t) + \epsilon_{model}(t)
\]

Use a deterministic worst-case bound and, where data permits, a stochastic oscillator model tied to measured stability statistics. Report when external-consistency latency or throughput violates configured service-level objectives and when the architecture must use logical clocks, local ordering domains, or weaker semantics.

Timing-source compromise, spoofing, partition, and common-mode failure shall also be evaluated in the adversary model.

### 3.9 Supervisory span and credential economics

#### 3.9.1 Span of control

For supervisory span k:

\[
L = \left\lceil \log_k N \right\rceil
\]

with L = 0 at N = 1. Tabulate L for:

\[
k \in \{4,8,16\}
\]

across the full scale ladder.

At each supervisory layer, model:

- Alert arrival rate
- Aggregation and suppression
- Escalation probability
- Reviewer count
- Reviewer service-time distribution
- Queue discipline
- Automation false-positive and false-negative rates
- Human review capacity where humans remain in the loop

Report the first layer to cross \(\rho = 0.70\), \(0.90\), and \(1.00\), plus the resulting detection and containment delay.

#### 3.9.2 Keys, certificates, and revocation

Compute pairwise symmetric-key count:

\[
K_{pairwise} = \binom{N}{2}
\]

At N = 10,000, verify the exact value.

Compare:

- Pairwise symmetric keying
- Logical key hierarchy with explicit rekey operations per membership change
- Per-workload short-lived certificates with issuance rate:

\[
\lambda_{cert} = \frac{N}{TTL}
\]

At N = 10,000 and TTL = 300 seconds, compute the steady-state issuance rate, then add renewal jitter, overlap, retry, failure, and burst factors.

Model:

- Mass revocation of m agents
- Certificate-authority and hardware-security-module signing capacity
- Status or revocation propagation
- Verification load at relying parties
- Audit-log load
- Issuer quorum failure
- Issuer compromise
- Recovery time
- Credential replay and cloning when key non-exportability is absent

Size the issuing authority using p95 and p99 burst demand plus a declared headroom factor, not mean demand alone.

### 3.10 Cost and energy per useful task

Define a transparent cost model containing at minimum:

- Compute
- Memory
- Storage
- Network transport and egress
- Cryptographic operations
- Identity and key-management operations
- Control-plane service capacity
- Human supervisory labor
- Incident response and recovery
- Failed or repeated tasks

All cost rates shall be measured, cited, inferred, or notional. Report cost and practical energy per useful task, with the denominator defined in Section 1.3. Separate the Landauer floor from practical dissipation.

---

## 4. Adversary and Failure Model

State cryptographic, timing, identity-root, and operational assumptions before making any security claim.

Model at minimum:

1. **Dolev-Yao network adversary:** Can read, drop, delay, reorder, replay, and inject network messages, but cannot break the selected cryptographic primitives. State explicitly that no protocol can guarantee liveness under permanent partition or unbounded message suppression. Evaluate liveness only under a declared bounded-outage, partial-synchrony, or recovery assumption.
2. **Byzantine subset:** Up to f agents or control-plane replicas deviate arbitrarily and may collude.
3. **Credentialed insider:** Holds valid credentials for a subset of capabilities and attempts capability abuse, privilege expansion, or lateral movement.
4. **Correlated supply-chain compromise:** A fraction s of images, dependencies, or hardware components are compromised before deployment through a common latent cause. Use a correlated model such as a beta-binomial, hierarchical latent variable, or explicitly defined common-cause event.
5. **Instruction-channel manipulation:** Adversarial input causes black-box policy deviation within or beyond held capabilities. Parameterize this through externally measured or notional response distributions, not assumptions about a particular model architecture.
6. **Sybil attack:** Attempts to inflate N with unauthorized identities. Model issuance gates, attestation, enrollment review, and denial-of-service load.
7. **Control-plane compromise:** Identity, authorization, policy, telemetry, or revocation services are corrupted or unavailable.
8. **Telemetry deception:** Agents suppress, delay, forge, or selectively report telemetry.
9. **Timing attack:** Timing sources are spoofed, delayed, partitioned, or driven into holdover, including correlated failure of supposedly diverse sources.
10. **Kill-channel denial:** Revocation or termination commands are blocked, delayed, or acknowledged falsely.
11. **Resource-exhaustion attack:** Adversary targets queues, credential issuance, consensus leaders, storage, or reviewers.
12. **Targeted graph attack:** Adversary selects high-degree, high-centrality, supervisory, or issuer nodes rather than random nodes.
13. **Operator or automation error:** Non-malicious policy, configuration, or response errors create equivalent assurance failures.

For each adversary and failure class, report distributions of:

- Time to detect
- Time to classify
- Time to authorize response
- Time to contain
- Time to recover
- Agent-count blast radius
- Capability-weighted blast radius
- Mission-impact-weighted blast radius
- Useful-task loss
- Control-plane load

Evaluate single attacks, coordinated attacks, low-and-slow attacks, and burst attacks. State adversary budget, knowledge, and stopping conditions.

---

## 5. Scale Ladder and Experimental Design

### 5.1 Scale ladder

Execute the study at:

\[
N \in \{1,10,100,1{,}000,10{,}000,30{,}000,100{,}000\}
\]

Use full agent-based simulation where feasible. For approximation cases, validate the approximation against full simulation at N = 1,000 and at the largest additional feasible N. Report approximation error by metric and refuse to use the approximation for metrics it does not reproduce adequately.

### 5.2 Independent variables

Cover all of the following:

- \(G_c\) topology
- \(G_a\) topology
- Dependency concentration and common-mode structure in \(G_d\)
- Supervisory topology and span in \(G_s\)
- Coordination regime: independent, pairwise, coalition-forming, hierarchical
- Consistency regime: global linearizable, shard-local linearizable, causal, eventual
- Segmentation policy: none, flat tenancy, m-way partition, dynamic microsegmentation, capability-degree cap
- Detection and remediation rate \(\gamma_{rec}\)
- Infection or compromise rate \(\beta_{inf}\)
- Authorization-boundary traversal probability q
- Clock uncertainty \(\epsilon\)
- Control-plane replication R and server count c
- Credential lifetime and renewal policy
- Telemetry rate, compression, and aggregation span
- Controller gain and delay
- Adversary class and budget
- Geographic distribution and latency

Each variable shall appear in at least one controlled experiment. Do not imply that every possible combination was tested unless it actually was.

### 5.3 Staged design of experiments

Use this staged design:

#### Stage 0: Analytic and software verification

- Unit tests for formulas and graph metrics
- M/M/1 and M/M/c queue checks
- Gossip growth check
- Consensus message-count checks on small n
- Percolation checks on known graph families
- Deterministic replay checks

No substantive fleet result may be published if Stage 0 fails.

#### Stage 1: Parameter screening

Use Latin hypercube sampling or Morris screening for broad continuous-parameter exploration. Stratify or block by categorical architecture family. Identify influential parameters and interactions.

#### Stage 2: Global sensitivity

Use a Saltelli or other Sobol-compatible sampling design for continuous variables. Report first-order and total-order Sobol indices with confidence intervals. Do not claim Sobol indices were produced from an ordinary Latin hypercube design. Handle categorical variables with separate strata, functional ANOVA, permutation importance, or another justified method.

#### Stage 3: Threshold-focused experiments

Perform targeted factorial or response-surface experiments around:

- USL retrograde points
- Queue utilization cliffs
- Epidemic thresholds
- Percolation thresholds
- Controller stability boundaries
- Observability ceilings
- Credential burst saturation
- Timing service-level violations

#### Stage 4: Scale-ladder architecture comparison

Run the complete scale ladder for the most informative architecture variants selected from earlier stages. Include at least:

- Flat dense coordination and authorization
- Dense communication with sparse segmented authorization
- Hierarchical coordination and supervision
- Sharded linearizable state with eventual fleet state
- Dynamic microsegmentation

Evaluate all five required graph families. At N up to 1,000, evaluate all 25 \(G_c\) and \(G_a\) topology pairings unless the feasibility analysis demonstrates a prohibitive cost. At larger N, use a justified subset emphasizing same-topology baselines and deliberately divergent communication-versus-authorization structures.

#### Stage 5: Adversarial and rare-event stress

Run targeted compromise, correlated supply-chain, issuer, timing, kill-channel, and Sybil scenarios. Use rare-event methods, importance sampling, or substantially increased replications when estimating low-probability, high-impact tail events.

#### Stage 6: Large-scale approximation checks

Run N = 30,000 and N = 100,000 using validated approximations or sparse event simulation. Compare extrapolated constraints with smaller-scale observed trends and identify any finite-size effects.

### 5.4 Dependent variables

Report all of the following where applicable:

- Useful-task throughput
- Raw throughput
- Coordination overhead as message, byte, CPU, and latency fractions
- p50, p95, and p99 end-to-end latency
- Control-plane utilization by service center
- Queue length and waiting-time distributions
- Mean and tail time to detect
- Mean and tail time to contain
- Blast-radius distributions
- Authorization-decision latency
- False permit and false deny rates
- Credential operations per second
- Availability under f Byzantine or crash faults
- Consensus decision rate and message volume
- Fitted \(\alpha\), \(\beta\), and \(N^*\)
- Spectral radius and epidemic stability product
- Percolation threshold estimates
- Telemetry ingest and anomaly-detection performance
- Controller margins and settling time
- Timing uncertainty and ordered-operation rate
- Practical energy per useful task
- Cost per useful task

### 5.5 Statistical rigor

Use at least 30 independent replications per reported stochastic configuration. Thirty is a minimum, not proof of precision. Continue replications until the primary metric reaches a declared relative or absolute confidence-interval half-width target, or until a declared computational cap is reached. Report cases that fail the precision target.

Use separate methods for terminating and steady-state simulations:

- For steady-state queueing and throughput runs, determine warmup using Welch's method, MSER-5, or a justified alternative. Use batch means only after checking batch independence and autocorrelation.
- For terminating experiments such as epidemic spread, gossip coverage, revocation storms, and fault transients, do not discard warmup. Compute uncertainty across independent replications.
- For p99 latency, use sufficient within-run event counts and a justified quantile confidence method such as bootstrap or order-statistic intervals.

Use common random numbers when comparing architecture variants and when stochastic streams can be meaningfully coupled. Use named independent random-number substreams for workload, service, network, graph generation, compromise, detection, and recovery.

Record every seed. Use a deterministic random generator such as NumPy PCG64DXSM with SeedSequence-based substreams. Ensure deterministic event ordering for equal timestamps.

Separate aleatory simulation uncertainty from epistemic input-parameter uncertainty. Apply multiple-comparison correction when making many simultaneous claims. Report effect sizes, not only p-values.

---

## 6. Implementation and Reproducibility Requirements

### 6.1 Language and libraries

Use Python 3.11 or later.

Required core libraries:

- SimPy or an explicit deterministic event queue
- NumPy
- SciPy
- NetworkX
- pandas
- PyArrow for columnar data
- Matplotlib for publication figures
- SALib or a justified equivalent for sensitivity analysis
- pytest for verification

For the interactive visual environment, use an offline-capable local Python stack such as:

- Plotly and Dash with all assets served locally, or
- Panel, Bokeh, HoloViews, and Datashader

No visualization, map, font, JavaScript, or data dependency may require a network call at runtime. Do not use a content-delivery network.

### 6.2 Repository structure

Use a structure equivalent to:

```text
fleet-assurance-sim/
  README.md
  pyproject.toml
  lockfile
  CITATION.cff
  LICENSE
  configs/
    baselines/
    experiments/
    visualization/
  src/fleet_sim/
    model/
    graphs/
    workloads/
    control_plane/
    consensus/
    security/
    timing/
    telemetry/
    experiments/
    analysis/
    visualization/
    provenance/
  tests/
    unit/
    integration/
    statistical/
    replay/
  data/
    generated/
    external/
  results/
  figures/
  replay_bundles/
  paper/
  manifests/
  docs/
```

Separate the simulation model, experiment runner, analysis, and visualization. The visualization shall consume event logs and snapshots. It shall not alter simulation state or scientific results.

### 6.3 Determinism and environment capture

Given a seed and a pinned environment, repeated execution shall be deterministic. Record:

- Source-control commit hash
- Dirty-tree status
- Python version
- Operating system and architecture
- Dependency versions and hashes
- CPU and available memory
- Configuration hash
- Random seeds and substream identifiers
- Start and end timestamps
- Wall-clock duration
- Trace level
- Approximation mode

Cross-platform floating-point execution may not be bit-identical. Claim bit reproducibility only where demonstrated. Otherwise require numerical reproducibility within declared tolerances under a pinned container or environment.

Provide a lockfile and a container definition. Generate a software bill of materials. The simulation shall make no external network calls during execution.

### 6.4 Event model and trace schema

Use an append-only event log as the canonical source for replay. At minimum, each event shall contain:

- run_id
- configuration_hash
- seed
- event_id
- parent_event_id or causal predecessor where applicable
- simulation_time
- logical_time
- event_type
- source_id
- destination_id or resource_id
- graph_layer
- task_id
- coalition_id
- message_id
- message_bytes
- capability_id
- authorization_decision
- credential_id or credential epoch
- state_before
- state_after
- severity
- policy_version
- timing_uncertainty
- provenance tag

Store high-volume event data in partitioned Parquet. Produce periodic state snapshots and event deltas so replay can seek without replaying from time zero.

Support trace levels:

1. Metrics only
2. Summary events
3. Security and control events
4. Full event trace

Scientific results shall state which trace level was used. Trace level shall not change model behavior.

### 6.5 Scale and approximation

Benchmark full agent-based execution at N = 1,000 and N = 10,000. State the reference hardware and wall-clock budget.

If full tracing at N = 10,000 is too costly, retain full model behavior while using summary-event tracing for the experiment matrix, and execute at least one canonical N = 10,000 full-trace scenario if feasible. Measure trace overhead.

If a mean-field, fluid, branching-process, or aggregate approximation is required:

- Derive it.
- State assumptions.
- Validate it against full simulation.
- Report metric-by-metric error.
- Mark every result produced by the approximation.
- Do not use the approximation for tail or topology-sensitive metrics unless validation supports it.

### 6.6 Verification before validation

At minimum, implement automated checks for:

- M/M/1 and M/M/c formulas
- Little's Law residual
- Graph generation statistics
- Consensus message counts
- Gossip growth
- Percolation thresholds on known families
- Epidemic extinction in clearly subcritical cases
- Epidemic persistence or large outbreaks in clearly supercritical finite-size cases
- Clock-error growth under fixed fractional-frequency error
- Credential issuance rate
- Replay-state equivalence
- Seed determinism

A failed verification test blocks publication of dependent results.

### 6.7 Secure scientific software practices

- Validate all configuration inputs against schemas.
- Do not execute arbitrary code from configuration files.
- Do not embed secrets.
- Pin dependencies.
- Produce an SBOM.
- Log model and policy versions.
- Fail closed on invalid parameters or missing provenance.
- Use type annotations and automated linting.
- Include unit, integration, statistical, and replay tests.

---

## 7. Interactive Virtual Visualization and Replay Environment

Build an offline interactive application named the **Virtual Fleet Assurance Console**. It is a visual experiment and replay environment. Do not call it a validated digital twin unless it has been calibrated against a real deployment.

### 7.1 Required operating modes

The application shall provide:

1. **Live mode:** Display a currently executing simulation. Live rendering may use adaptive aggregation to avoid materially slowing the simulation.
2. **Replay mode:** Deterministically reconstruct a completed run from its event log and snapshots.
3. **Comparison mode:** Replay two or more runs on a synchronized timeline and show metric deltas.
4. **Scenario mode:** Configure a new experiment from validated controls. Any change creates a new configuration hash and run identifier. A recorded replay is immutable.

### 7.2 Primary visual views

Provide at minimum:

#### A. Fleet topology view

Show agents, resources, control-plane services, supervisors, partitions, and geographic regions. Allow independent toggles for:

- Communication graph \(G_c\)
- Authorization graph \(G_a\)
- Dependency graph \(G_d\)
- Supervisory graph \(G_s\)
- Derived attack-reachability graph \(G_x(t)\)

Never display these layers as though they are interchangeable. Use distinct accessible visual encodings and a persistent legend.

#### B. Dynamic event animation

Animate or otherwise visibly indicate:

- Task arrival and dispatch
- Coalition formation and dissolution
- Message exchange
- Gossip propagation
- Consensus phases and quorum formation
- Queue buildup and service completion
- Credential issuance, renewal, expiration, and revocation
- Detection, suspicion, quarantine, kill, and recovery
- Compromise propagation
- Authorization-boundary traversal
- Timing degradation and holdover
- Autoscaling and supervisory-loop oscillation

The viewer shall support pause, resume, single-event step, fixed-time step, variable playback speed, and timeline scrubbing.

#### C. Node and edge inspection

Selecting an agent, resource, service, or edge shall show:

- Identity and credential epoch
- Capability manifest summary
- Current health and compromise state
- Supervisor and partition
- Queue state
- Current task and coalition
- Recent messages and authorization decisions
- Timing uncertainty
- Telemetry status
- Causal event history
- Applicable graph-layer relationships

#### D. Control-plane operations view

Show per-service-center:

- Arrival rate
- Service rate
- Server count
- Utilization
- Queue length
- Wait-time percentiles
- Replication state
- Consensus state
- Failure and recovery state

Mark utilization thresholds and service-level violations visibly.

#### E. Security and containment view

Show:

- Current compromised, suspected, isolated, revoked, and recovered populations
- Largest reachable authorization or attack component
- Spectral radius
- Epidemic stability product
- Effective reproduction metric
- Percolation state
- Blast-radius distribution
- Detection and containment timers
- High-centrality attack paths

Provide a mode that highlights the difference between communication reachability and authorization reachability.

#### F. Supervisory hierarchy view

Show the hierarchy as a collapsible tree or sunburst-style structure. Display:

- Span and depth
- Alert arrival and service rates
- Queue saturation by layer
- Escalation paths
- Human-versus-automated review
- Kill-authority path
- Common-mode supervisor dependencies

#### G. Telemetry and observability view

Show:

- Raw and aggregated telemetry rate by layer
- Compression ratio
- Channel utilization
- Dropped, delayed, or summarized telemetry
- Rate-distortion operating point
- Anomaly false-positive and false-negative rate
- Classes of anomalies hidden by aggregation

#### H. Geographic and timing view

Use an offline map or abstract geographic coordinate plane. Show:

- Agent and control-plane location
- Physical-distance latency floor
- Route-stretch and observed simulated latency
- Clock uncertainty by node or region
- Timing-source dependencies
- Holdover duration
- External-consistency commit-wait contribution

Do not require an online map service. An optional 3D spatial view may be included for demonstrations, but the exact 2D graph, hierarchy, and geographic views remain authoritative because 3D layouts can obscure adjacency and scale.

#### I. Scaling and assurance-envelope view

Display synchronized plots for:

- Useful throughput versus N with USL fit and \(N^*\)
- Latency percentile fans
- Queue utilization cliffs
- Consensus messages and bytes
- Spectral radius and epidemic threshold
- Blast-radius CDF
- Telemetry bandwidth and observability ceiling
- Ordered-operation throughput versus clock uncertainty
- Credential issuance and revocation load
- Cost and energy per useful task

Indicate which assurance constraints are satisfied or violated without collapsing them into one opaque score.

### 7.3 Adaptive level of detail

The visualization shall remain truthful and usable at scale.

- For N up to 1,000, support exact node rendering and exact selected edge rendering.
- For N from 1,001 through 10,000, render all nodes when feasible, but use edge bundling, edge sampling, partition summaries, and on-demand neighborhood expansion.
- Above N = 10,000, default to aggregation by partition, supervisory branch, geographic region, role, or degree class. Allow exact drill-down into selected subgraphs.
- Never attempt to draw every edge of a dense 10,000-node complete graph.

Every view shall label its representation as one of:

- Exact
- Sampled
- Aggregated
- Mean-field or approximated

Metrics must be computed from the scientific result data, not estimated from what is visible on screen.

### 7.4 Visual experiment controls

Provide controls for:

- N and scale rung
- Workload archetype
- \(G_c\), \(G_a\), \(G_d\), and \(G_s\) configuration
- Coordination and consistency regime
- Segmentation policy
- Detection and remediation rate
- Compromise rate
- Boundary-failure probability
- Consensus protocol and committee size
- Credential TTL
- Telemetry rate and compression
- Supervisory span
- Controller gain and delay
- Clock uncertainty and holdover start
- Geographic distribution
- Adversary type, start time, target-selection rule, and budget
- Random seed

Controls shall display units, bounds, provenance class, and whether a value is measured, inferred, or notional.

### 7.5 Fault injection

Permit controlled injection of:

- Agent crash
- Byzantine behavior
- Network partition
- Link delay or loss
- Credential compromise
- Issuer outage
- Supervisor compromise
- Telemetry suppression
- Timing-source denial or spoofing
- Revocation-channel failure
- Sybil enrollment surge
- Correlated supply-chain activation

Fault injection into an existing recorded replay is not allowed. It must create a new run so results remain reproducible.

### 7.6 Replay correctness

The replay engine shall be scientifically verifiable.

Implement tests showing:

- Final replay state hash equals final simulation state hash.
- Event counts match by type.
- No events are silently dropped.
- Seeking to time t from a snapshot plus deltas matches replay from time zero.
- Small deterministic scenarios match golden expected frames and state transitions.
- Comparison mode aligns runs by simulation time and clearly handles differing termination times.

Visualization failure shall not alter or invalidate raw simulation data. Any display decimation shall be disclosed.

### 7.7 Demonstration scenarios

Provide deterministic replay bundles for at least these scenarios:

1. Flat all-to-all coordination reaching a USL retrograde point.
2. Hierarchical coordination maintaining useful throughput while adding depth latency.
3. Gossip dissemination reaching 99 percent coverage.
4. Authorization-graph percolation crossing critical q.
5. Dynamic microsegmentation holding compromise subcritical.
6. PBFT-class view change under Byzantine or failed leader behavior.
7. Credential rekey or revocation storm.
8. Supervisory-loop thrashing caused by excessive gain and delay.
9. Timing denial causing holdover growth and ordered-operation degradation.
10. Telemetry compression hiding a selected anomaly class.
11. Sybil surge saturating identity issuance.
12. Correlated supply-chain compromise bypassing independent-failure assumptions.

Each replay bundle shall include the configuration, seed, event log or compact replay data, final metrics, and a short expected-observation guide.

### 7.8 Visual exports

Provide:

- Local launch command
- Offline browser application
- Self-contained or locally bundled replay package
- Static PNG and SVG publication figures
- Animated GIF or HTML animation fallback
- MP4 or WebM export when a local encoder is available
- Screenshot capture for paper figures

Every exported animation shall include run ID, configuration hash, seed, N, scenario name, and whether the display is exact, sampled, aggregated, or approximated.

---

## 8. Falsifiable Hypotheses

State these before executing the study. Report support, refutation, or indeterminate evidence. A refuted hypothesis is a valid and useful result.

### H1: Retrograde scaling in flat coordination

**H1a, analytic:** Under the USL form, \(\beta > 0\) and \(\alpha < 1\) imply a finite retrograde point.

**H1b, empirical:** Under the declared low, mixed, and high-coordination parameter ranges, flat all-to-all coordination yields \(N^* < 10^3\). This numerical threshold is not implied merely by \(\beta > 0\) and may be refuted.

### H2: Hierarchical scaling

Hierarchical aggregation with bounded span restores near-linear useful-throughput scaling to N = 10,000 for the low and mixed workload archetypes, with latency proportional to supervisory depth and a measurable observability cost.

### H3: Spectral containment

Under the specified SIS approximation and stochastic compromise model, keeping:

\[
\frac{\beta_{inf}}{\gamma_{rec}}\lambda_{max}(A) < 1
\]

keeps compromise subcritical as N grows, provided segmentation keeps spectral radius bounded and common-mode paths in \(G_d\) and \(G_s\) do not bypass \(G_a\). The result is conditional on the attack-path model, not fleet size alone.

### H4: Linearizability ceiling

The rate of fleet-wide linearizable operations and the size of their consensus committees, rather than agent count by itself, determine the consensus ceiling.

### H5: Supervisory growth-rate ceiling

For burst fleet growth and attack transients, supervisory sensing, decision, and actuation settling time becomes binding before raw compute capacity in at least the mixed and high-coordination workload archetypes.

### H6: Timing as a load-bearing dependency

Degradation of bounded physical-time assurance reduces external-consistency throughput and increases latency according to the protocol-specific commit-wait model. Causal consistency remains available through logical clocks but with weaker real-time guarantees.

### H7: Observability ceiling

For a specified source, distortion metric, anomaly-detection requirement, and channel bottleneck, observability imposes a lower maximum manageable N than compute or consensus in at least one workload archetype. This is a conditional empirical hypothesis, not a universal theorem.

---

## 9. Required Deliverables

1. **Simulation source:** Structured as specified, with a README that reproduces every reported result from a clean pinned environment.
2. **Parameter and provenance registry:** Machine-readable, complete, and traceable to results.
3. **Results dataset:** Columnar format containing full configuration, seed, metric, uncertainty, provenance, and execution manifest.
4. **Static figure set:** Publication-quality figures with exact configuration, run IDs, sample size, and replication count in every caption.
5. **Virtual Fleet Assurance Console:** Offline interactive live, replay, comparison, and scenario environment.
6. **Replay bundles:** Deterministic demonstrations listed in Section 7.7.
7. **Technical paper:** Doctoral technical standard, with formal model, assumptions, derivations, numerical results, validity limits, adversarial analysis, and the required section titled "What This Study Does Not Establish."
8. **Reference architecture candidate:** Specific topology, segmentation, consistency regime, consensus committee size, span of control, credential lifetime, detection rate, timing budget, observability design, and control-plane sizing required for N = 10,000 under each declared workload archetype.
9. **Decision table:** For each scale rung, identify binding constraint, control-plane sizing, required architecture, uncertainty, and first failure mode if the recommendation is not followed.
10. **Verification and validation report:** Tests, tolerances, failures, approximation validation, replay validation, and unresolved defects.
11. **Requirements traceability matrix:** Maps every binding prompt requirement to implementation and evidence.
12. **Model card and limitations register:** Intended use, out-of-scope use, assumptions, provenance, known weaknesses, and prohibited interpretations.

### 9.1 Minimum static figures

Produce at minimum:

- Useful throughput versus N by architecture, with USL fit and \(N^*\)
- Latency percentile fans
- Control-plane utilization and queue cliffs
- Consensus message and byte scaling
- Blast-radius CDFs by segmentation policy
- Epidemic threshold phase diagram over \((\beta_{inf}/\gamma_{rec}, \lambda_{max})\)
- Largest-component fraction versus q
- Telemetry ingest versus N for flat and hierarchical designs
- Detection performance versus compression or distortion
- Ordered-operation throughput versus clock uncertainty
- Supervisory saturation by layer
- Credential issuance and revocation burst curves
- Controller stability and thrashing region
- Sobol first-order and total-order sensitivity bars
- Cost and energy per useful task

### 9.2 Conditional recommendation language

If material inputs remain notional, title the recommendation:

> Candidate reference architecture under the stated notional parameter set

Do not present it as a universally validated production architecture.

---

## 10. Acceptance Gates

### Gate A: Feasibility

- Configuration count, runtime, storage, and precision targets documented.
- Staged experimental plan selected.

### Gate B: Verification

- All analytic baseline and deterministic tests pass.
- Failures block dependent conclusions.

### Gate C: Reproducibility

- Clean-environment run reproduces selected canonical metrics within declared tolerance.
- Manifests and seeds are complete.

### Gate D: Statistical validity

- Replication and confidence targets met or shortfalls explicitly reported.
- Warmup and batch methods used only where applicable.
- Sensitivity method matches sampling design.

### Gate E: Visualization integrity

- Replay state equals simulation state.
- Exact, sampled, aggregated, and approximated displays are labeled.
- Visualization does not alter model execution.

### Gate F: Security-claim discipline

- Every security claim states adversary, assumptions, and evidence class.
- No modeled architecture is called secure solely because it remained inside the simulated envelope.

### Gate G: Final quality

- Requirements traceability is complete.
- No uncited measured value appears.
- No notional value is presented as measured.
- No missing result is replaced by plausible prose.
- No em dash appears in any deliverable.

---

## 11. Style and Framing Constraints

- Use formal technical register at doctoral standard.
- Show derivations and assumptions in full.
- Use precise units and dimensional checks.
- Use the term "assurance" rather than "trust" except when quoting a source that uses different language.
- Refer to boundaries as authorization boundaries or assurance boundaries.
- Do not use em dashes.
- Frame the architecture as a version-zero strawman for community critique.
- Use strong conclusions only where supported by evidence.
- State uncertainty, conflicting evidence, and model limits directly.
- Distinguish theorem, model-specific approximation, numerical result, measurement, inference, notional assumption, and conjecture.
- Every figure, table, statistic, and recommendation shall be traceable to a source, parameter registry entry, configuration hash, run ID, or analytic derivation.

---

## 12. Required Paper Section: What This Study Does Not Establish

Include the following text verbatim, then expand it with study-specific limitations:

A discrete-event simulation establishes the behavior of a model. Its findings transfer to a real deployment only to the degree that the model's assumptions hold. This study cannot establish that any particular implementation is secure. It establishes structural constraints: which architectures are ruled out by mathematics and physics, and which remain candidates. Ruling out is stronger than ruling in. An architecture that violates the epidemic threshold condition or exceeds the observability ceiling is provably unmanageable at the stated scale. An architecture that satisfies every constraint identified here is merely not yet ruled out, and still requires adversarial testing, formal verification of critical components, and operational evaluation before deployment.

The phrase "unlimited agents" should be retired in favor of the precise finding this study will produce: fleets scale without bound only along axes where required coordination is O(1) or O(log N) in fleet size, and every remaining axis has a computable ceiling.

The expansion shall state that the required verbatim paragraph does not convert an approximate epidemic threshold into a universal theorem. Identify which threshold statements are exact, which are bounds, and which are mean-field or finite-size approximations. Use the phrase "provably unmanageable" elsewhere only when an actual proof or rigorous bound supports it under the stated assumptions.

The expansion shall also address:

- Runtime-agnostic modeling limits
- Unknown or unmodeled policy behavior
- Parameter uncertainty and notional inputs
- Finite-size and approximation error
- Common-mode failures
- Unknown zero-day vulnerabilities
- Human and organizational behavior
- Real cryptographic implementation defects
- Environmental and mission changes
- Visualization abstraction and aggregation
- The difference between structural feasibility and production authorization

---

## 13. Final Response Order

When the work is complete, present results in this order:

1. Completion status and exact scope executed
2. Executive findings
3. Binding constraints by scale rung
4. Hypothesis outcomes
5. Analytic versus simulated comparison
6. Candidate N = 10,000 reference architectures by workload archetype
7. Adversary and blast-radius findings
8. Timing and observability findings
9. Statistical confidence and sensitivity
10. Verification, validation, and approximation error
11. Virtual visualization launch and replay instructions
12. Requirements traceability summary
13. What the study does not establish
14. Reproduction commands and artifact index

Do not claim completion until the source, manifests, datasets, figures, visual console, replay bundles, paper, and traceability artifacts exist and have passed the applicable acceptance gates.
