/* PyExplain — simple one-button controller */
(function () {
  const $ = (s) => document.querySelector(s);
  const stage = $("#stage");
  const state = { script: null, theme: "cartoon", total: 0, playing: false,
                  cfg: null, jobId: null };

  const SAMPLE = `# A simple program to check if you can watch a movie
name = input("What's your name? ")
age = int(input("How old are you? "))

if age >= 13:
    print("Hi " + name + ", you can watch this PG-13 movie!")
else:
    years_left = 13 - age
    print("Sorry " + name + ", come back in " + str(years_left) + " years!")`;

  /* ---------- editor gutter ---------- */
  const code = $("#code"), gutter = $("#gutter");
  function syncGutter() {
    const lines = code.value.split("\n").length || 1;
    gutter.innerHTML = Array.from({ length: lines }, (_, i) => i + 1).join("<br>");
    $("#code-stat").textContent = `${lines} line${lines === 1 ? "" : "s"}`;
  }
  code.addEventListener("input", syncGutter);
  code.addEventListener("scroll", () => { gutter.scrollTop = code.scrollTop; });
  code.addEventListener("keydown", (e) => {
    if (e.key === "Tab") { e.preventDefault();
      const s = code.selectionStart;
      code.value = code.value.slice(0, s) + "    " + code.value.slice(code.selectionEnd);
      code.selectionStart = code.selectionEnd = s + 4; syncGutter(); }
  });
  $("#sample-btn").onclick = () => { code.value = SAMPLE; syncGutter(); };

  /* ---------- config / setup ---------- */
  async function loadConfig() {
    try { state.cfg = await (await fetch("/api/config")).json(); }
    catch (e) { state.cfg = { has_anthropic: false, has_elevenlabs: false }; }
    if (state.cfg.style) { state.theme = state.cfg.style; $("#style").value = state.cfg.style; }
    if (state.cfg.target_sec) $("#length").value = String(state.cfg.target_sec);
    // show setup automatically until both keys exist
    if (!state.cfg.has_anthropic || !state.cfg.has_elevenlabs) showSetup(true);
    if (state.cfg.has_elevenlabs) loadVoices();
  }

  async function loadVoices() {
    try {
      const d = await (await fetch("/api/voices", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: "{}" })).json();
      if (!d.ok || !d.voices) return;
      const sel = $("#voice"); sel.innerHTML = "";
      d.voices.forEach(v => { const o = document.createElement("option");
        o.value = v.voice_id; o.textContent = v.name; sel.appendChild(o); });
      if (d.current) sel.value = d.current;
    } catch (e) {}
  }
  $("#voice").onchange = () => {
    const v = $("#voice").value; if (!v) return;
    fetch("/api/config", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voice_id: v }) });
  };
  function showSetup(on) { $("#setup").style.display = on ? "block" : "none"; }
  $("#gear").onclick = () => showSetup($("#setup").style.display === "none");

  $("#save-keys").onclick = async () => {
    const body = {};
    if ($("#anthropic-key").value.trim()) body.anthropic_key = $("#anthropic-key").value.trim();
    if ($("#eleven-key").value.trim()) body.elevenlabs_key = $("#eleven-key").value.trim();
    $("#setup-msg").textContent = "Saving…";
    try {
      state.cfg = await (await fetch("/api/config", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();
      $("#anthropic-key").value = ""; $("#eleven-key").value = "";
      $("#setup-msg").textContent = "Saved ✓";
      if (state.cfg.has_anthropic) { showSetup(false); clearErr(); }
    } catch (e) { $("#setup-msg").textContent = "Could not save."; }
  };

  $("#style").onchange = () => { state.theme = $("#style").value;
    post({ type: "control", action: "theme", value: state.theme }); };

  /* ---------- preview messaging ---------- */
  function post(msg) { try { stage.contentWindow.postMessage(msg, "*"); } catch (e) {} }
  function loadPreview() {
    $("#stage-empty").style.display = "none";
    $("#transport").style.display = "flex";
    post({ type: "load-script", script: state.script,
           opts: { theme: state.theme, audio: state.audio } });
    state.playing = true; setPlayIcon();
  }
  window.addEventListener("message", (e) => {
    const d = e.data || {};
    if (d.type === "engine-ready") state.total = d.total;
    if (d.type === "engine-tick") { state.total = d.total;
      $("#scrub").value = Math.round((d.t / d.total) * 1000);
      $("#time").textContent = fmt(d.t) + " / " + fmt(d.total); }
    if (d.type === "engine-ended") { state.playing = false; setPlayIcon(); }
  });
  const fmt = (ms) => { const s = Math.floor(ms / 1000); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
  function setPlayIcon() { $("#play-btn").textContent = state.playing ? "❚❚" : "▶"; }
  $("#play-btn").onclick = () => { state.playing = !state.playing;
    post({ type: "control", action: state.playing ? "play" : "pause" }); setPlayIcon(); };
  $("#restart-btn").onclick = () => { state.playing = true;
    post({ type: "control", action: "restart" }); setPlayIcon(); };
  $("#scrub").oninput = () => post({ type: "control", action: "seek",
    value: (+$("#scrub").value / 1000) * state.total });

  /* ---------- the one button ---------- */
  $("#create-btn").onclick = async () => {
    clearErr(); hideResult();
    if (!code.value.trim()) return showErr("Paste some Python code first.");
    if (!state.cfg || !state.cfg.has_anthropic) { showSetup(true);
      return showErr("Add your Claude API key once in Setup, then press Create Video."); }

    const btn = $("#create-btn"); btn.disabled = true; const lbl = btn.textContent;
    state.audio = null;
    try {
      // 1) author the script with Claude
      showJob("Writing the script…", "Claude is directing your video, scene by scene");
      btn.textContent = "Working…";
      const ar = await fetch("/api/author", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: code.value, brief: $("#brief").value,
          target_sec: +$("#length").value }) });
      const script = await ar.json();
      if (!script.ok) throw new Error(script.error || "Could not write the script.");
      state.script = script;
      state.theme = (script.meta && script.meta.style) || state.theme;
      loadPreview();                          // instant animated preview

      // 2) narration (only if an ElevenLabs key is set)
      let jobId = null;
      const wantAudio = !!(state.cfg && state.cfg.has_elevenlabs);
      if (wantAudio) {
        showJob("Recording narration…", "Synthesizing the voiceover with ElevenLabs");
        const nr = await fetch("/api/narrate", { method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ script: state.script }) });
        const nj = await nr.json();
        if (nj.error) throw new Error(nj.error);
        const narrated = await pollJob(nj.job_id, "Recording narration…",
          (j) => "Scene " + Math.round((j.frac || 0) * state.script.scenes.length) +
                 " of " + state.script.scenes.length);
        if (narrated.status === "error") throw new Error(narrated.error);
        state.script = narrated.script;
        state.audio = (narrated.script.audio || []).filter(Boolean).length ? narrated.script.audio : null;
        jobId = nj.job_id;
        loadPreview();                        // refresh preview with synced audio
      }

      // 3) render the MP4 (Manim if available, else quick — auto fallback)
      showJob("Producing the video…", "Rendering animation frames and encoding the MP4");
      const rr = await fetch("/api/render", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ script: state.script, job_id: jobId, with_audio: wantAudio,
          theme: state.theme }) });
      const rj = await rr.json();
      if (rj.error) throw new Error(rj.error);
      const done = await pollJob(rj.job_id, "Producing the video…", stageMsg);
      if (done.status === "error") throw new Error(done.error);
      showResult(done.video_url);
    } catch (e) {
      hideJob(); showErr(humanError(String(e.message || e)));
    } finally { btn.disabled = false; btn.textContent = lbl; }
  };

  function stageMsg(j) {
    const map = { rendering: "Painting animation frames", mixing: "Mixing the soundtrack",
      encoding: "Encoding the final MP4", starting: "Warming up", done: "Finishing up" };
    let s = (map[j.stage] || j.stage || "Working");
    return s + "…";
  }

  async function pollJob(id, title, subFn) {
    return new Promise((resolve) => {
      const tick = async () => {
        try {
          const j = await (await fetch("/api/job/" + id)).json();
          const pct = Math.round((j.frac || 0) * 100);
          $("#job-title").textContent = title; $("#job-pct").textContent = pct + "%";
          $("#bar-fill").style.width = pct + "%";
          $("#job-sub").textContent = subFn ? subFn(j) : "";
          if (j.status === "done" || j.status === "narrated" || j.status === "error") return resolve(j);
        } catch (e) {}
        setTimeout(tick, 600);
      };
      tick();
    });
  }

  /* ---------- job / result / errors ---------- */
  function showJob(t, sub) { $("#job").style.display = "block"; $("#job-title").textContent = t;
    $("#job-sub").textContent = sub || ""; $("#job-pct").textContent = "0%"; $("#bar-fill").style.width = "0%"; }
  function hideJob() { $("#job").style.display = "none"; }
  function showResult(url) { hideJob(); $("#result").style.display = "flex";
    $("#result-video").src = url; $("#download").href = url; }
  function hideResult() { $("#result").style.display = "none"; }
  function humanError(m) {
    if (/Claude API key/i.test(m)) { showSetup(true); }
    return m;
  }
  function showErr(m) { const e = $("#err"); e.style.display = "block"; e.textContent = m; }
  function clearErr() { $("#err").style.display = "none"; }

  /* init */
  code.value = SAMPLE; syncGutter();
  loadConfig();
})();
