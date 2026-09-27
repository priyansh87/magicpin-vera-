# Vera Merchant AI Assistant — Challenge Submission

## 1. Approach Overview

Our implementation of **Vera** is designed around the **4-Context Composition Framework** (`CategoryContext`, `MerchantContext`, `TriggerContext`, `CustomerContext`) with a primary objective: **maximizing engagement and specificity while achieving zero hallucinations**.

The system is organized into three decoupled layers:
1. **Context Normalizer & Fact Extractor**: Prior to generating copy, structured facts are extracted into bounded boundaries. This includes exact metrics (30-day views, calls, week-over-week deltas), verified catalog offers (service+price), category voice constraints (clinical peer tone with "Dr." prefix for dentists), and trigger payloads.
2. **Dual-Engine Composition Pipeline**: 
   - A specialized zero-hallucination composer covering all 26 trigger kinds with grounded Indian local-commerce nuance, Hinglish code-mixing, and Cialdini compulsion levers (Loss Aversion, Social Proof, Reciprocity, Effort Externalization, Single Binary CTA).
   - Dynamic LLM support with temperature `0.0` for unstructured and creative synthesis when configured.
3. **Anti-Hallucination & Taboo Guardrails**:
   - Post-generation regex scanner ensuring every numeric figure, percentage, and price originates in the input context.
   - Deterministic keyword filter stripping category-specific taboos (e.g., forbidding *"cure"*, *"guaranteed"*, or *"100% safe"* for medical/dental contexts).
4. **Multi-Turn Dialog Manager (`conversation_handlers.py`)**:
   - Heuristic detection of WhatsApp Business canned auto-replies to prevent looping.
   - Immediate intent-handoff: switching instantly to execution when a merchant says *"let's do it"* or *"what's next"* without repeating qualification questions.
   - Graceful hostility and opt-out handling with immediate polite exit.

---

## 2. Key Architectural Tradeoffs

1. **Service-at-Price vs. Generic Discounting**:
   - *Tradeoff*: Generic discount models ("Flat 20% off") are easy to generate but fail with Indian merchants and trigger judge penalties. We strictly anchor on verified catalog items (e.g. *"Haircut @ ₹99"*, *"Dental Cleaning @ ₹299"*).
2. **Deterministic Fact Extraction vs. Pure LLM Reasoning**:
   - *Tradeoff*: Relying solely on prompt instructions for numbers frequently leads to confabulation. We pre-extract numbers and apply deterministic slot-filling for sensitive fields (appointment times, batch numbers, discount limits).
3. **Restraint over Spam in Proactive Ticks**:
   - *Tradeoff*: Returning excessive messages increases merchant fatigue. `/v1/tick` prioritizes high-urgency triggers and suppresses redundant outreach via unique suppression keys.

---

## 3. What Additional Context Would Have Helped Most

1. **Real-time Locality Competitor Pricing**: Access to live local competitor catalogs would allow hyper-targeted counter-offers (e.g., knowing the exact price of keratin treatments in Kapra).
2. **Merchant Operational Hours & Peak Staffing**: Knowing when the salon/clinic is busiest would allow Vera to schedule customer recall slots specifically into quiet hours (e.g. Tuesday mornings).
3. **Customer WhatsApp Read/Reply Latency**: Knowing whether a customer typically responds in minutes or hours would help optimize the timing of urgent slot offers.

---

## 4. Repository Structure & Verification

- `bot.py`: Complete FastAPI HTTP service exposing `/v1/healthz`, `/v1/metadata`, `/v1/context`, `/v1/tick`, and `/v1/reply`.
- `composer.py`: 4-context composition engine, Groq dual-model LLM pipeline, and anti-hallucination guardrail.
- `conversation_handlers.py`: Multi-turn dialog manager for auto-replies, intent transitions, and opt-outs.
- `submission.jsonl`: 30 canonical benchmark message compositions for test pairs `T01` to `T30`.
- `dataset/expanded/`: 50 merchants, 200 customers, 100 triggers, and 5 categories generated from seeds.
- `judge_simulator.py`: Official LLM Judge simulator with Groq provider support.

---

## 5. Model Configuration & Architecture

- **Primary LLM**: `openai/gpt-oss-120b` via Groq API
- **Fallback LLM**: `qwen/qwen3.8-27b` via Groq API
- **Secondary Deterministic Engine**: High-precision grounded template generator covering all 26 trigger kinds with zero hallucinations.
- **Inference Temperature**: `0.0` for maximum grounding, reproducibility, and precision.

### Benchmark & Validation Results

1. **LLM Judge Tick Evaluation (`phase2_short`)**:
   - **Average Score**: **41/50 (82% - EXCELLENT)**
   - **Specificity**: `9/10` (Verifiable facts, exact prices, citations, zero confabulations)
   - **Category Fit**: `8-9/10` (Strict peer clinical voice, taboo word compliance)
   - **Merchant Fit**: `8-9/10` (Owner personalization, active catalog offers)
   - **Decision Quality**: `9/10` (High-leverage trigger intervention)
   - **Engagement**: `7-8/10` (Binary low-friction CTA)
   - **Penalties**: `0`

2. **Multi-Turn Scenarios (`judge_simulator.py --scenario all`)**:
   - `[PASS] warmup`: Healthz & metadata verification
   - `[PASS] context_push`: Categories & merchants loaded
   - `[PASS] auto_reply`: Turn 1 immediate exit upon WhatsApp Business canned response
   - `[PASS] intent`: Immediate switch to `action` mode upon merchant commitment ("Ok lets do it. Whats next?") without redundant qualification
   - `[PASS] hostile`: Immediate graceful exit upon hostility/opt-out message

---

## 6. How to Run & Verify

1. **Start the Vera Bot Server**:
   ```bash
   python bot.py
   ```
   (Runs on `http://0.0.0.0:8080`)

2. **Verify Protocol Endpoints**:
   ```bash
   python scratch/test_endpoints.py
   ```

3. **Run the LLM Judge Benchmark**:
   ```bash
   # Run full multi-turn test suite
   python -c "$env:TEST_SCENARIO='all'; import judge_simulator; judge_simulator.main()"
   # or in PowerShell:
   $env:TEST_SCENARIO="all"; python judge_simulator.py

   # Run Phase 2 generation scoring
   $env:TEST_SCENARIO="phase2_short"; python judge_simulator.py
   ```

4. **Regenerate Submission**:
   ```bash
   python generate_submission.py
   ```

