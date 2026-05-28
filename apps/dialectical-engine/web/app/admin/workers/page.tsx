"use client";

import { useEffect, useState } from "react";
import { backendStatus } from "@/lib/api";
import { AuthGate } from "@/components/AuthGate";
import type { WorkerStatus } from "@/lib/types";

export default function WorkersPage() {
  return <AuthGate>{() => <WorkersView />}</AuthGate>;
}

function WorkersView() {
  const [workers, setWorkers] = useState<WorkerStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const rows = await backendStatus();
        if (active) {
          setWorkers(rows);
          setError(null);
          setLastUpdated(new Date());
        }
      } catch (exc) {
        if (active) setError(exc instanceof Error ? exc.message : "Unable to load worker status");
      }
    }
    load();
    const timer = window.setInterval(load, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const onlineWorkers = workers.filter((worker) => worker.status === "online");
  const degradedWorkers = workers.filter((worker) => worker.status === "degraded");
  const offlineWorkers = workers.filter((worker) => worker.status === "offline");
  const workerB = workers.find(isWorkerB);
  const workerBState = workerB?.status ?? "missing";
  const capabilities = Array.from(new Set(workers.flatMap((worker) => worker.capabilities))).sort();
  const topologyLabel = deploymentTopology(onlineWorkers.length, workerBState);

  return (
    <main className="page">
      <div className="pageHeader">
        <div>
          <h1>Workers</h1>
          <p className="muted">Live status, capabilities, current job, and heartbeat time.</p>
        </div>
      </div>
      <div className="workerSummary" aria-label="Worker deployment summary">
        <div className="workerMetric">
          <span>Topology</span>
          <strong>{topologyLabel}</strong>
        </div>
        <div className="workerMetric">
          <span>Online</span>
          <strong>{onlineWorkers.length}</strong>
        </div>
        <div className="workerMetric">
          <span>Degraded</span>
          <strong>{degradedWorkers.length}</strong>
        </div>
        <div className="workerMetric">
          <span>Offline</span>
          <strong>{offlineWorkers.length}</strong>
        </div>
        <div className="workerMetric">
          <span>Worker B</span>
          <strong>{workerBState}</strong>
        </div>
        <div className="workerMetric">
          <span>Capabilities</span>
          <strong>{capabilities.length}</strong>
        </div>
        <div className="workerMetric">
          <span>Refreshed</span>
          <strong>{lastUpdated ? lastUpdated.toLocaleTimeString() : "Pending"}</strong>
        </div>
      </div>
      {error ? <div className="error">{error}</div> : null}
      <div className="workersTableWrap">
        <table className="workersTable">
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Current Job</th>
              <th>Last Seen</th>
              <th>Capabilities</th>
            </tr>
          </thead>
          <tbody>
            {workers.length === 0 ? (
              <tr>
                <td colSpan={5}>No workers registered.</td>
              </tr>
            ) : (
              workers.map((worker) => (
                <tr key={worker.id}>
                  <td>{worker.name}</td>
                  <td>
                    <span className={`statusPill ${workerStatusClass(worker.status)}`}>{worker.status}</span>
                  </td>
                  <td>{worker.current_job_id || "Idle"}</td>
                  <td>{new Date(worker.last_seen).toLocaleString()}</td>
                  <td>
                    <div className="capabilities">
                      {worker.capabilities.map((capability) => (
                        <span className="badge" key={capability}>
                          {capability}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}

function isWorkerB(worker: WorkerStatus): boolean {
  const name = worker.name.toLowerCase();
  return name.includes("adesso") || name.includes("worker-b") || name.includes("worker b");
}

function deploymentTopology(onlineWorkers: number, workerBState: string): string {
  if (onlineWorkers >= 2 && workerBState === "online") return "Two-worker topology online";
  if (onlineWorkers >= 2) return "Two workers online";
  if (onlineWorkers === 1) return "Single-worker mode";
  return "No workers online";
}

function workerStatusClass(status: string): string {
  if (status === "online") return "statusOnline";
  if (status === "degraded") return "statusDegraded";
  if (status === "offline") return "statusOffline";
  return "";
}
