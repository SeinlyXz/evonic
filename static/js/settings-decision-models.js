/* Decision Profiles admin pane. Keeps Playground selection in URL state only; it never invokes a model. */
window.decisionModels = {
    profiles: [],
    models: [],

    async init() {
        await this.load();
        this.renderPlayground();
        this.bindPlayground();
    },

    async load() {
        const status = document.getElementById("decision-profiles-status");
        try {
            const [profilesData, models] = await Promise.all([
                apiGet("/api/admin/decision-profiles"),
                ModelsCache.get(),
            ]);
            this.profiles = profilesData.profiles || [];
            this.models = models || [];
            this.render();
        } catch (error) {
            status.textContent = "Could not load Decision Profiles. Refresh and try again.";
            status.className = "rounded border border-red-300 bg-red-50 dark:bg-red-950/30 dark:border-red-800 p-4 text-sm text-red-800 dark:text-red-200";
        }
    },

    compatibleModels() {
        return this.models.filter((model) => {
            const decision = model.capabilities && model.capabilities.decision;
            return model.enabled && decision && decision.enabled &&
                Array.isArray(decision.schema_versions) && decision.schema_versions.includes("decision-schema/v1");
        });
    },

    render() {
        const status = document.getElementById("decision-profiles-status");
        const list = document.getElementById("decision-profiles-list");
        if (!this.profiles.length) {
            status.textContent = "No Decision Profiles yet. Create one to configure a reusable structured decision.";
            status.className = "rounded border border-dashed border-gray-300 dark:border-gray-600 p-5 text-sm text-gray-600 dark:text-gray-300";
            list.innerHTML = "";
            return;
        }
        status.textContent = "";
        status.className = "hidden";
        list.innerHTML = this.profiles.map((profile) => this.card(profile)).join("");
    },

    card(profile) {
        const state = profile.enabled ? "Enabled" : "Disabled";
        const stateClass = profile.enabled ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300" : "bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300";
        const key = this.escape(profile.profile_key);
        return `<article class="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 space-y-3">
          <div class="flex items-start justify-between gap-3"><div><h3 class="font-semibold text-gray-900 dark:text-gray-100">${this.escape(profile.display_name)}</h3><p class="text-xs text-gray-500 dark:text-gray-400 font-mono">${key}</p></div><span class="rounded px-2 py-1 text-xs font-medium ${stateClass}">${state} · ${this.escape(profile.mode)}</span></div>
          <p class="text-sm text-gray-600 dark:text-gray-300">${this.escape(profile.description || "No description provided.")}</p>
          <dl class="grid grid-cols-2 gap-2 text-xs text-gray-500 dark:text-gray-400"><div><dt>Schema</dt><dd class="font-medium text-gray-700 dark:text-gray-200">${this.escape(profile.schema_version)}</dd></div><div><dt>Policy</dt><dd class="font-medium text-gray-700 dark:text-gray-200">${this.escape(profile.policy_version)}</dd></div><div><dt>Primary</dt><dd class="font-medium text-gray-700 dark:text-gray-200 truncate">${this.escape(profile.primary_model_id)}</dd></div><div><dt>Fallback</dt><dd class="font-medium text-gray-700 dark:text-gray-200 truncate">${this.escape(profile.fallback_model_id || "None")}</dd></div></dl>
          <div class="flex flex-wrap gap-2"><button type="button" class="btn-secondary text-sm" onclick="decisionModels.edit('${key}')">Edit</button><button type="button" class="btn-secondary text-sm" onclick="decisionModels.openPlayground({profile: '${key}'})">Open in Playground</button><button type="button" class="btn-secondary text-sm" onclick="decisionModels.toggle('${key}')">${profile.enabled ? "Deactivate" : "Enable"}</button>${!this.isBuiltin(profile.profile_key) ? `<button type="button" class="text-sm text-red-600 dark:text-red-400" onclick="decisionModels.remove('${key}')">Delete</button>` : ""}</div>
        </article>`;
    },

    isBuiltin(key) { return ["safety.command", "agent.task_complexity", "agent.path_boundary", "agent.goal_completion"].includes(key); },
    escape(value) { const el = document.createElement("div"); el.textContent = value == null ? "" : String(value); return el.innerHTML; },

    modelOptions(selected, includeEmpty) {
        const compatible = this.compatibleModels();
        const options = compatible.map((model) => `<option value="${this.escape(model.id)}" ${model.id === selected ? "selected" : ""}>${this.escape(model.name)} (${this.escape(model.id)})</option>`);
        return (includeEmpty ? '<option value="">No fallback</option>' : '<option value="" disabled selected>Select a compatible model</option>') + options.join("");
    },

    openCreate() {
        document.getElementById("decision-profile-form").reset();
        document.getElementById("decision-profile-modal-title").textContent = "New Decision Profile";
        document.getElementById("decision-profile-revision").value = "";
        document.getElementById("decision-profile-key").disabled = false;
        document.getElementById("decision-profile-primary").innerHTML = this.modelOptions(null, false);
        document.getElementById("decision-profile-fallback").innerHTML = this.modelOptions(null, true);
        document.getElementById("decision-profile-schema").value = JSON.stringify({version: "decision-schema/v1", fields: [{key: "approved", kind: "boolean"}]}, null, 2);
        this.clearError();
        openModal("decision-profile-modal");
    },

    edit(key) {
        const profile = this.profiles.find((item) => item.profile_key === key);
        if (!profile) return;
        document.getElementById("decision-profile-modal-title").textContent = "Edit Decision Profile";
        document.getElementById("decision-profile-revision").value = profile.revision;
        const fields = {"decision-profile-key":"profile_key", "decision-profile-name":"display_name", "decision-profile-description":"description", "decision-profile-mode":"mode", "decision-profile-policy":"policy_version"};
        Object.entries(fields).forEach(([id, field]) => document.getElementById(id).value = profile[field] || "");
        document.getElementById("decision-profile-key").disabled = true;
        document.getElementById("decision-profile-enabled").checked = profile.enabled;
        document.getElementById("decision-profile-primary").innerHTML = this.modelOptions(profile.primary_model_id, false);
        document.getElementById("decision-profile-fallback").innerHTML = this.modelOptions(profile.fallback_model_id, true);
        document.getElementById("decision-profile-timeout").value = profile.timeout_ms;
        document.getElementById("decision-profile-retries").value = profile.retry_limit;
        document.getElementById("decision-profile-confidence").value = profile.minimum_confidence;
        document.getElementById("decision-profile-schema").value = JSON.stringify(profile.schema, null, 2);
        this.clearError();
        openModal("decision-profile-modal");
    },

    payload() {
        return {profile_key: document.getElementById("decision-profile-key").value.trim(), display_name: document.getElementById("decision-profile-name").value.trim(), description: document.getElementById("decision-profile-description").value.trim(), enabled: document.getElementById("decision-profile-enabled").checked, mode: document.getElementById("decision-profile-mode").value, schema_version: "decision-schema/v1", policy_version: document.getElementById("decision-profile-policy").value.trim(), schema: JSON.parse(document.getElementById("decision-profile-schema").value), primary_model_id: document.getElementById("decision-profile-primary").value, fallback_model_id: document.getElementById("decision-profile-fallback").value || null, timeout_ms: Number(document.getElementById("decision-profile-timeout").value), retry_limit: Number(document.getElementById("decision-profile-retries").value), minimum_confidence: Number(document.getElementById("decision-profile-confidence").value)};
    },

    async save(event) {
        event.preventDefault();
        let data;
        try { data = this.payload(); } catch (error) { this.showError("schema: must be valid JSON."); return; }
        const revision = document.getElementById("decision-profile-revision").value;
        try {
            const response = revision ? await apiPut("/api/admin/decision-profiles/" + encodeURIComponent(data.profile_key), {...data, revision: Number(revision)}) : await apiPost("/api/admin/decision-profiles", data);
            if (!response.success) { this.showError((response.error && response.error.path ? response.error.path + ": " : "") + ((response.error && response.error.message) || "Could not save profile.")); return; }
            closeModal("decision-profile-modal"); await this.load(); if (window.toast) toast.show("Decision Profile saved", "success");
        } catch (error) { this.showError("Could not save profile. Check the values and try again."); }
    },

    showError(message) { const el = document.getElementById("decision-profile-error"); el.textContent = message; el.classList.remove("hidden"); },
    clearError() { document.getElementById("decision-profile-error").classList.add("hidden"); },

    async toggle(key) { const profile = this.profiles.find((item) => item.profile_key === key); if (!profile) return; const data = {...profile, enabled: !profile.enabled, mode: !profile.enabled && profile.mode === "off" ? "shadow" : profile.mode, revision: profile.revision}; const response = await apiPut("/api/admin/decision-profiles/" + encodeURIComponent(key), data); if (!response.success) { if (window.toast) toast.show((response.error && response.error.message) || "Could not update profile", "error"); return; } await this.load(); },
    async remove(key) { if (!(await showConfirm({title: "Delete Decision Profile", message: "Delete this application profile? This cannot be undone.", confirmText: "Delete"}))) return; const response = await apiDelete("/api/admin/decision-profiles/" + encodeURIComponent(key)); if (!response.success) { if (window.toast) toast.show((response.error && response.error.message) || "Could not delete profile", "error"); return; } await this.load(); },
    openPlayground(context) { const params = new URLSearchParams(context); history.replaceState(null, "", "#decision-playground?" + params.toString()); SettingsNav.activate("decision-playground"); this.renderPlayground(context); },
    playgroundDefaultSchema() { return {version: "decision-schema/v1", fields: [{key: "priority", kind: "choice", description: "Operational priority", choices: ["HIGH", "LOW"]}, {key: "requires_review", kind: "boolean", description: "Whether a human should review this incident"}]}; },
    playgroundSchema() { return JSON.parse(document.getElementById("playground-schema").value); },
    playgroundSetSchema(schema) { document.getElementById("playground-schema").value = JSON.stringify(schema, null, 2); this.renderSchemaBuilder(schema); },
    renderPlayground(context) {
        const box = document.getElementById("decision-playground-context"); if (!box) return;
        const query = context || Object.fromEntries(new URLSearchParams(location.hash.split("?", 2)[1] || ""));
        const profileSelect = document.getElementById("playground-profile"), modelSelect = document.getElementById("playground-model");
        if (!profileSelect || !modelSelect) return;
        profileSelect.innerHTML = this.profiles.map(p => `<option value="${this.escape(p.profile_key)}">${this.escape(p.display_name)} (${this.escape(p.profile_key)})</option>`).join("");
        modelSelect.innerHTML = this.compatibleModels().map(m => `<option value="${this.escape(m.id)}">${this.escape(m.name)} (${this.escape(m.id)})</option>`).join("");
        if (query.profile) { document.getElementById("playground-mode").value = "profile"; profileSelect.value = query.profile; }
        if (query.model) { document.getElementById("playground-mode").value = "direct"; modelSelect.value = query.model; }
        if (!document.getElementById("playground-schema").value) this.playgroundSetSchema(this.playgroundDefaultSchema());
        this.playgroundModeChanged();
        box.textContent = "Inference only: no shell, Python, tool, webhook, or configuration changes can run from this Playground. Inputs and provider responses are not retained.";
    },
    bindPlayground() {
        const mode = document.getElementById("playground-mode"), schema = document.getElementById("playground-schema"), profile = document.getElementById("playground-profile");
        if (!mode || mode.dataset.bound) return; mode.dataset.bound = "1";
        mode.addEventListener("change", () => this.playgroundModeChanged());
        profile.addEventListener("change", () => this.playgroundProfileChanged());
        schema.addEventListener("input", () => { try { this.renderSchemaBuilder(this.playgroundSchema()); this.playgroundError(""); } catch (_) { this.playgroundError("schema: must be valid JSON before it can be run."); } });
    },
    playgroundModeChanged() {
        const direct = document.getElementById("playground-mode").value === "direct";
        document.getElementById("playground-profile-wrap").classList.toggle("hidden", direct); document.getElementById("playground-model-wrap").classList.toggle("hidden", !direct);
        if (!direct) this.playgroundProfileChanged(); else { try { this.renderSchemaBuilder(this.playgroundSchema()); } catch (_) {} }
    },
    playgroundProfileChanged() { const profile = this.profiles.find(p => p.profile_key === document.getElementById("playground-profile").value); if (profile) this.playgroundSetSchema(profile.schema); },
    renderSchemaBuilder(schema) {
        const root = document.getElementById("playground-schema-builder"); if (!root || !schema || !Array.isArray(schema.fields)) return;
        root.innerHTML = schema.fields.map((field, index) => `<div class="rounded border border-gray-200 dark:border-gray-700 p-3 grid grid-cols-1 md:grid-cols-6 gap-2 items-end"><div><label class="text-xs">Key</label><input data-field="key" data-index="${index}" value="${this.escape(field.key || "")}" class="w-full border rounded px-2 py-1 dark:bg-gray-700"></div><div><label class="text-xs">Type</label><select data-field="kind" data-index="${index}" class="w-full border rounded px-2 py-1 dark:bg-gray-700"><option value="choice" ${field.kind === "choice" ? "selected" : ""}>Choice</option><option value="boolean" ${field.kind === "boolean" ? "selected" : ""}>Boolean / null</option><option value="score" ${field.kind === "score" ? "selected" : ""}>Score</option></select></div><div class="md:col-span-2"><label class="text-xs">Description</label><input data-field="description" data-index="${index}" value="${this.escape(field.description || "")}" class="w-full border rounded px-2 py-1 dark:bg-gray-700"></div><div class="${field.kind === "choice" ? "" : "hidden"}"><label class="text-xs">Choices (comma-separated)</label><input data-field="choices" data-index="${index}" value="${this.escape((field.choices || []).join(", "))}" class="w-full border rounded px-2 py-1 dark:bg-gray-700"></div><div class="${field.kind === "score" ? "" : "hidden"}"><label class="text-xs">Range</label><div class="flex gap-1"><input type="number" step="any" aria-label="Minimum score" data-field="minimum" data-index="${index}" value="${field.minimum == null ? 0 : field.minimum}" class="w-1/2 border rounded px-2 py-1 dark:bg-gray-700"><input type="number" step="any" aria-label="Maximum score" data-field="maximum" data-index="${index}" value="${field.maximum == null ? 1 : field.maximum}" class="w-1/2 border rounded px-2 py-1 dark:bg-gray-700"></div></div><div class="flex gap-2"><label class="text-xs"><input type="checkbox" data-field="nullable" data-index="${index}" ${field.nullable ? "checked" : ""}> Nullable</label><button type="button" class="text-red-600 text-xs" data-remove="${index}">Remove</button></div></div>`).join("");
        root.querySelectorAll("input, select").forEach(el => el.addEventListener("change", event => this.playgroundFieldChanged(event))); root.querySelectorAll("[data-remove]").forEach(el => el.addEventListener("click", () => { const s = this.playgroundSchema(); s.fields.splice(Number(el.dataset.remove), 1); this.playgroundSetSchema(s); }));
    },
    playgroundFieldChanged(event) { const el = event.target, schema = this.playgroundSchema(), field = schema.fields[Number(el.dataset.index)], name = el.dataset.field; if (!field || !name) return; if (name === "nullable") field[name] = el.checked; else if (name === "choices") field.choices = el.value.split(",").map(v => v.trim()).filter(Boolean); else if (name === "minimum" || name === "maximum") field[name] = Number(el.value); else field[name] = el.value; if (name === "kind") { delete field.choices; delete field.minimum; delete field.maximum; if (field.kind === "choice") field.choices = ["YES", "NO"]; if (field.kind === "score") { field.minimum = 0; field.maximum = 1; } } this.playgroundSetSchema(schema); },
    playgroundAddField() { const schema = this.playgroundSchema(); schema.fields.push({key: `field_${schema.fields.length + 1}`, kind: "boolean", description: ""}); this.playgroundSetSchema(schema); },
    playgroundPreset() { this.playgroundSetSchema(this.playgroundDefaultSchema()); document.getElementById("playground-input").value = JSON.stringify({incident: "Payment-service outage affecting checkout", impact: "Customers cannot complete purchases"}, null, 2); },
    playgroundReset() { this.playgroundSetSchema(this.playgroundDefaultSchema()); document.getElementById("playground-input").value = "{}"; document.getElementById("playground-result").textContent = "No test has run. Input and raw provider responses are not retained."; this.playgroundError(""); },
    playgroundError(message) { const el = document.getElementById("playground-error"); if (!message) { el.textContent = ""; el.classList.add("hidden"); return; } el.textContent = message; el.classList.remove("hidden"); },
    async playgroundRun() { let schema, input; try { schema = this.playgroundSchema(); input = JSON.parse(document.getElementById("playground-input").value); if (!input || Array.isArray(input) || typeof input !== "object") throw new Error("input_context must be a JSON object"); } catch (error) { this.playgroundError(error.message || "Schema and input must be valid JSON objects."); return; } const direct = document.getElementById("playground-mode").value === "direct"; const payload = {mode: direct ? "direct" : "profile", input_context: input}; if (direct) Object.assign(payload, {model_id: document.getElementById("playground-model").value, schema}); else payload.profile_key = document.getElementById("playground-profile").value; const button = document.getElementById("playground-run"); button.disabled = true; button.textContent = "Running…"; this.playgroundError(""); try { const response = await apiPost("/api/admin/decision-playground/run", payload); if (!response.success) { this.playgroundError((response.error && ((response.error.path ? response.error.path + ": " : "") + response.error.message)) || "Test could not run."); return; } this.renderPlaygroundResult(response.result); } catch (_) { this.playgroundError("Test could not run. Refresh and try again."); } finally { button.disabled = false; button.textContent = "Run safe test"; } },
    renderPlaygroundResult(result) { const root = document.getElementById("playground-result"), error = result.error; if (error) { root.innerHTML = `<div class="text-red-700 dark:text-red-300"><strong>${this.escape(error.code)}</strong>: ${this.escape(error.message)}${error.retryable ? " You can try again." : ""}</div>`; return; } const fields = (result.fields || []).map(field => `<li class="rounded border border-gray-200 dark:border-gray-700 p-3"><div class="font-medium">${this.escape(field.key)}: <code>${this.escape(JSON.stringify(field.value))}</code></div><div class="text-xs text-gray-500">Confidence: ${field.confidence == null ? "unavailable" : this.escape(Math.round(field.confidence * 100) + "%")} · Candidates: ${field.candidates && field.candidates.length ? this.escape(JSON.stringify(field.candidates)) : "unavailable"} · Provider logits: ${field.provider_logits && field.provider_logits.length ? this.escape(JSON.stringify(field.provider_logits)) : "unavailable (not supplied by adapter)"}</div></li>`).join(""); root.innerHTML = `<div class="space-y-3"><div class="rounded bg-emerald-50 dark:bg-emerald-950/30 p-3 text-emerald-800 dark:text-emerald-200">Normalized decision completed.</div><ul class="space-y-2">${fields}</ul><details><summary class="cursor-pointer font-medium">Execution details</summary><pre class="mt-2 overflow-auto rounded bg-gray-100 dark:bg-gray-900 p-3 text-xs">${this.escape(JSON.stringify({profile: result.profile, provider: result.provider, timing: result.timing, attempts: result.attempts, fallback: result.fallback, warnings: result.warnings, candidate_scores: result.display && result.display.candidate_scores, provider_logits: result.display && result.display.provider_logits}, null, 2))}</pre></details><details><summary class="cursor-pointer font-medium">Normalized JSON</summary><pre class="mt-2 overflow-auto rounded bg-gray-100 dark:bg-gray-900 p-3 text-xs">${this.escape(JSON.stringify(result, null, 2))}</pre></details></div>`; this.lastPlaygroundResult = result; },
    async playgroundCopy() { if (!this.lastPlaygroundResult) return; try { await navigator.clipboard.writeText(JSON.stringify(this.lastPlaygroundResult, null, 2)); if (window.toast) toast.show("Normalized result copied", "success"); } catch (_) { this.playgroundError("Could not copy the result."); } },
};
