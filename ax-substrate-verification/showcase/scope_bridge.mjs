#!/usr/bin/env node
// Scope Bridge: Feeds external AX & Substrate verification events into Substrate Scope
// Allows showcasing test execution, worker bays, and snapshot lineage live in Scope UI.

const SCOPE_URL = process.env.SCOPE_URL || 'http://127.0.0.1:8123';

async function sendActivity(agent, kind, text, ms = 50) {
  try {
    await fetch(`${SCOPE_URL}/activity`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent, kind, text, ms, via: 'verification-harness' })
    });
  } catch (err) {
    // Scope might be starting up
  }
}

async function sendQueue(waitingAgents) {
  try {
    await fetch(`${SCOPE_URL}/queue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ waiting: waitingAgents.map(name => ({ name })) })
    });
  } catch (err) {}
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function runLiveShowcaseFeed() {
  console.log(`Connecting to Substrate Scope at ${SCOPE_URL}...`);
  await sleep(1500);

  console.log('📡 Broadcasting verification suite stages to Scope drawer...');

  // Stage 1: AX PostgreSQL Persistence & Reconciler
  await sendActivity('ax-postgres-store', 'prompt', 'Verify PostgreSQL persistence & leased locks schema...');
  await sleep(800);
  await sendActivity('ax-postgres-store', 'reply', 'PASS: schema.sql tasks jsonb & locks lease verified.', 120);
  await sleep(800);

  // Stage 2: Direct Substrate Actor Observation
  await sendActivity('ax-orchestrator', 'prompt', 'Query live actor status directly from Substrate...');
  await sleep(800);
  await sendActivity('ax-orchestrator', 'reply', 'PASS: Observed Substrate actor Running, IP 10.244.1.7; no cached drift.', 45);
  await sleep(800);

  // Stage 3: Credential Isolation
  await sendActivity('ax-sandbox-task', 'prompt', 'Inspect sandbox environment for ambient GEMINI_API_KEY...');
  await sleep(800);
  await sendActivity('ax-sandbox-task', 'reply', 'PASS: Zero ambient API keys injected into sandbox. Model proxy retains auth.', 80);
  await sleep(800);

  // Stage 4: Substrate OOM Isolation
  await sendActivity('substrate-gvisor-worker', 'prompt', 'Run bounded memory.pressure workload against target actor...');
  await sleep(1000);
  await sendActivity('substrate-gvisor-worker', 'error', 'Target actor throttled at memory.high and killed via cgroup.kill.', 210);
  await sleep(800);
  await sendActivity('substrate-gvisor-worker', 'reply', 'PASS: Peer actors on worker remain healthy and responsive.', 95);
  await sleep(800);

  // Stage 5: Snapshot Lineage & Guarded Tag Deletion
  await sendQueue(['clone-borrower-v1', 'task-branch-alpha']);
  await sendActivity('snapshot-lineage', 'prompt', 'Attempt deleting tag exp-tag-v1 while clone-borrower is borrowing snapshot...');
  await sleep(1200);
  await sendActivity('snapshot-lineage', 'error', 'Rejected: FAILED_PRECONDITION (Tag is in deleting state / active borrower guard).', 310);
  await sleep(800);
  await sendActivity('snapshot-lineage', 'reply', 'PASS: Lineage safety preserved. Borrowing actor remains recoverable.', 140);
  await sendQueue([]);

  console.log('✅ Showcase simulation broadcast complete.');
}

runLiveShowcaseFeed();
