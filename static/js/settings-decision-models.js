/* Decision Profiles admin pane. Keeps Playground selection in URL state only; it never invokes a model. */
window.decisionModels = {
    profiles: [],
    models: [],

    async init() {
        await this.load();
        this.renderPlayground();
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
    renderPlayground(context) { const box = document.getElementById("decision-playground-context"); if (!box) return; const query = context || Object.fromEntries(new URLSearchParams(location.hash.split("?", 2)[1] || "")); box.textContent = query.profile ? `Profile selected: ${query.profile}. Configure a future test here; nothing has run.` : query.model ? `Model selected: ${query.model}. Configure a future test here; nothing has run.` : "Choose a Decision Profile or decision-capable model to preselect it here. Nothing executes automatically."; },
};
