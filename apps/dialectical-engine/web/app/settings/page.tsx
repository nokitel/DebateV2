"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { AuthGate } from "@/components/AuthGate";

type SettingsPayload = {
  routing: unknown;
  configured_models: string[];
  enabled_models: string[];
  grok_monthly_cap_usd: number;
  grok_monthly_spend_usd: number;
  model_monthly_caps_usd?: Record<string, number>;
  model_monthly_spend_usd?: Record<string, number>;
};

export default function SettingsPage() {
  return <AuthGate>{(token) => <SettingsForm token={token} />}</AuthGate>;
}

function SettingsForm({ token }: { token: string }) {
  const [routing, setRouting] = useState("");
  const [modelCaps, setModelCaps] = useState<Record<string, string>>({});
  const [modelSpend, setModelSpend] = useState<Record<string, number>>({});
  const [configuredModels, setConfiguredModels] = useState<string[]>([]);
  const [enabledModels, setEnabledModels] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function syncSettings(payload: SettingsPayload) {
    const models = payload.configured_models.length ? payload.configured_models : payload.enabled_models;
    const caps = payload.model_monthly_caps_usd ?? { "grok-4": payload.grok_monthly_cap_usd };
    const spendByModel = payload.model_monthly_spend_usd ?? { "grok-4": payload.grok_monthly_spend_usd };
    setRouting(JSON.stringify(payload.routing, null, 2));
    setModelCaps(
      Object.fromEntries(
        models.map((model) => {
          const cap = caps[model];
          return [model, Number.isFinite(cap) ? String(cap) : ""];
        })
      )
    );
    setModelSpend(spendByModel);
    setConfiguredModels(models);
    setEnabledModels(new Set(payload.enabled_models.length ? payload.enabled_models : models));
  }

  useEffect(() => {
    apiFetch<SettingsPayload>("/api/settings", {}, token).then(syncSettings).catch((exc) => {
      setError(exc instanceof Error ? exc.message : "Unable to load settings");
    });
  }, [token]);

  function toggleModel(model: string) {
    setEnabledModels((current) => {
      const next = new Set(current);
      if (next.has(model)) {
        next.delete(model);
      } else {
        next.add(model);
      }
      return next;
    });
  }

  function updateModelCap(model: string, value: string) {
    setModelCaps((current) => ({ ...current, [model]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    let parsedRouting: unknown;
    try {
      parsedRouting = JSON.parse(routing);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Invalid routing JSON");
      return;
    }
    const selectedModels = configuredModels.filter((model) => enabledModels.has(model));
    const monthlyCaps: Record<string, number> = {};
    for (const model of configuredModels) {
      const value = modelCaps[model]?.trim() ?? "";
      if (!value) {
        continue;
      }
      const cap = Number(value);
      if (!Number.isFinite(cap) || cap < 0) {
        setError(`Invalid cap for ${model}`);
        return;
      }
      monthlyCaps[model] = cap;
    }
    const payload: {
      routing: unknown;
      model_monthly_caps_usd: Record<string, number>;
      grok_monthly_cap_usd?: number;
      enabled_models: string[];
    } = {
      routing: parsedRouting,
      model_monthly_caps_usd: monthlyCaps,
      enabled_models: selectedModels.length === configuredModels.length ? [] : selectedModels
    };
    if (monthlyCaps["grok-4"] !== undefined) {
      payload.grok_monthly_cap_usd = monthlyCaps["grok-4"];
    }
    try {
      const saved = await apiFetch<SettingsPayload>("/api/settings", { method: "PUT", body: JSON.stringify(payload) }, token);
      syncSettings(saved);
      setMessage("Saved");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to save settings");
    }
  }

  return (
    <main className="page">
      <div className="pageHeader">
        <div>
          <h1>Settings</h1>
          <p className="muted">Routing pools, enabled models, and monthly caps.</p>
        </div>
      </div>
      <form className="formPanel" onSubmit={submit}>
        {error ? <div className="error">{error}</div> : null}
        {message ? <div className="statusPill">{message}</div> : null}
        <div className="field">
          <label>Enabled models</label>
          <div className="modelToggleGrid">
            {configuredModels.map((model) => (
              <label className="modelToggle" key={model}>
                <input type="checkbox" checked={enabledModels.has(model)} onChange={() => toggleModel(model)} />
                <span>{model}</span>
              </label>
            ))}
          </div>
        </div>
        <div className="field">
          <label>Backend spend</label>
          <div className="spendGrid">
            {configuredModels.map((model) => (
              <div className="spendRow" key={model}>
                <span className="spendModel">{model}</span>
                <span className="spendValue">${(modelSpend[model] ?? 0).toFixed(4)}</span>
                <input
                  aria-label={`${model} monthly cap USD`}
                  type="number"
                  value={modelCaps[model] ?? ""}
                  min={0}
                  step="0.01"
                  placeholder="No cap"
                  onChange={(event) => updateModelCap(model, event.target.value)}
                />
              </div>
            ))}
          </div>
        </div>
        <div className="field">
          <label htmlFor="routing">Role routing JSON</label>
          <textarea id="routing" value={routing} onChange={(event) => setRouting(event.target.value)} />
        </div>
        <div className="toolbar">
          <button type="submit">Save</button>
        </div>
      </form>
    </main>
  );
}
