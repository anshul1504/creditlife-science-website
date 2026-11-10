/* Sign-in / sign-up / forgot-password / verify-email flow, shared by the popup and the popup-style pages. */
(function () {
  "use strict";
  var flow = document.querySelector("[data-flow]");
  var modalEl = document.getElementById("authModal");
  var modal = modalEl && window.bootstrap ? bootstrap.Modal.getOrCreateInstance(modalEl) : null;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Any link to the sign-in or sign-up page opens the popup (the pages themselves still work).
  document.addEventListener("click", function (e) {
    if (!modal || document.body.classList.contains("page-auth")) return;
    var a = e.target.closest("a[href]");
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || a.target === "_blank") return;
    var url;
    try { url = new URL(a.href, location.href); } catch (err) { return; }
    if (url.origin !== location.origin) return;
    if (url.pathname !== "/account/login/" && url.pathname !== "/account/register/") return;
    e.preventDefault();
    window.openAuth("login", url.searchParams.get("next") || (location.pathname + location.search));
  });

  if (!flow) return;

  var steps = flow.querySelectorAll("[data-step]");
  var alertBox = flow.querySelector("[data-flow-alert]");
  var boxesWrap = flow.querySelector("[data-otp-boxes]");
  var resetFields = flow.querySelector("[data-reset-fields]");
  var urls = {
    identify: flow.dataset.urlIdentify, request: flow.dataset.urlRequest, verify: flow.dataset.urlVerify, login: flow.dataset.urlLogin
  };
  var state = { email: "", purpose: "", extra: {}, next: flow.dataset.next || "", length: 6, timer: null, busy: false };
  var boxes = [];

  // ---------------------------------------------------------------- helpers
  function csrf() { return flow.querySelector("input[name=csrfmiddlewaretoken]").value; }
  function post(url, data) {
    var body = new URLSearchParams();
    Object.keys(data).forEach(function (k) { body.append(k, data[k]); });
    return fetch(url, {
      method: "POST", body: body, credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf(), "Content-Type": "application/x-www-form-urlencoded" }
    }).then(function (r) { return r.json().then(function (d) { return { status: r.status, ok: r.ok, data: d }; }); });
  }
  function setAlert(message) {
    if (!message) { alertBox.hidden = true; return; }
    alertBox.querySelector("span").textContent = message;
    alertBox.hidden = false;
  }
  function clearFieldErrors() {
    flow.querySelectorAll(".err-js").forEach(function (n) { n.remove(); });
    flow.querySelectorAll(".field.has-error").forEach(function (n) { n.classList.remove("has-error"); });
  }
  function fieldError(input, message) {
    var wrap = input && input.closest(".field");
    if (!wrap) return false;
    wrap.classList.add("has-error");
    var d = document.createElement("div");
    d.className = "err-js";
    d.innerHTML = '<i class="bi bi-exclamation-circle"></i>';
    d.appendChild(document.createTextNode(message));
    wrap.appendChild(d);
    return true;
  }
  function showErrors(form, data) {
    var general = [];
    var errors = data.errors || {};
    Object.keys(errors).forEach(function (key) {
      var input = key === "__all__" ? null : form.querySelector('[name="' + key + '"]');
      if (!fieldError(input, errors[key][0])) general = general.concat(errors[key]);
    });
    if (!general.length && !Object.keys(errors).length && data.message) general.push(data.message);
    setAlert(general.join(" "));
  }
  function show(step) {
    steps.forEach(function (s) { s.hidden = s.dataset.step !== step; });
    flow.dataset.current = step;
    setAlert("");
    clearFieldErrors();
    var section = flow.querySelector('[data-step="' + step + '"]');
    var first = section && section.querySelector("input:not([type=hidden]):not([type=checkbox])");
    if (step === "otp" && boxes.length) first = boxes[0];
    if (first && !window.matchMedia("(pointer: coarse)").matches) setTimeout(function () { first.focus(); }, 60);
  }
  function setBusy(form, on, text) {
    var btn = form.querySelector('button[type="submit"]');
    var label = btn && btn.querySelector("span");
    if (!btn) return;
    if (on) { btn.dataset.label = label.textContent; label.textContent = text || "Please wait..."; }
    else if (btn.dataset.label) { label.textContent = btn.dataset.label; }
    btn.disabled = on;
    state.busy = on;
  }
  function go(url) {
    if (url === location.pathname + location.search) location.reload(); else location.href = url;
  }
  function validEmail(v) { return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v); }

  // ------------------------------------------------------------- OTP boxes
  function buildBoxes(n) {
    boxesWrap.innerHTML = "";
    boxes = [];
    for (var i = 0; i < n; i++) {
      var input = document.createElement("input");
      input.type = "text"; input.inputMode = "numeric"; input.maxLength = 1; input.pattern = "[0-9]*";
      input.autocomplete = i === 0 ? "one-time-code" : "off";
      input.setAttribute("aria-label", "Digit " + (i + 1));
      boxesWrap.appendChild(input);
      boxes.push(input);
    }
    boxes.forEach(function (box, i) {
      box.addEventListener("input", function () {
        box.value = box.value.replace(/\D/g, "").slice(-1);
        boxesWrap.classList.remove("error");
        if (box.value && i < boxes.length - 1) boxes[i + 1].focus();
        if (code().length === boxes.length && state.purpose !== "reset") submitOtp();
      });
      box.addEventListener("keydown", function (e) {
        if (e.key === "Backspace" && !box.value && i > 0) { boxes[i - 1].focus(); boxes[i - 1].value = ""; }
        if (e.key === "ArrowLeft" && i > 0) boxes[i - 1].focus();
        if (e.key === "ArrowRight" && i < boxes.length - 1) boxes[i + 1].focus();
      });
      box.addEventListener("paste", function (e) {
        var text = (e.clipboardData || window.clipboardData).getData("text").replace(/\D/g, "");
        if (!text) return;
        e.preventDefault();
        text.slice(0, boxes.length).split("").forEach(function (d, k) { boxes[k].value = d; });
        boxes[Math.min(text.length, boxes.length) - 1].focus();
        if (code().length === boxes.length && state.purpose !== "reset") submitOtp();
      });
      box.addEventListener("focus", function () { box.select(); });
    });
  }
  function code() { return boxes.map(function (b) { return b.value; }).join(""); }
  function clearBoxes() { boxes.forEach(function (b) { b.value = ""; }); if (boxes[0]) boxes[0].focus(); }

  function startTimer(seconds) {
    var label = flow.querySelector("[data-resend-timer]");
    var button = flow.querySelector("[data-resend]");
    clearInterval(state.timer);
    var left = Math.max(0, parseInt(seconds, 10) || 0);
    function tick() {
      if (left > 0) {
        label.textContent = "Resend code in 0:" + (left < 10 ? "0" : "") + left;
        button.hidden = true;
        left -= 1;
      } else {
        clearInterval(state.timer);
        label.textContent = "Didn't get it? ";
        button.hidden = false;
      }
    }
    tick();
    state.timer = setInterval(tick, 1000);
  }

  // ------------------------------------------------------------ OTP steps
  var TITLES = { plogin: "Enter the code we texted you", login: "Enter your sign-in code", signup: "Verify your email", reset: "Reset your password", verify: "Verify your email" };
  var SUBMIT = { plogin: "Verify and sign in", login: "Verify and sign in", signup: "Verify and create account", reset: "Save new password", verify: "Verify email" };

  function showOtp(masked, cooldown, length) {
    state.length = length || state.length;
    buildBoxes(state.length);
    flow.querySelector("[data-otp-email]").textContent = masked || state.email;
    flow.querySelector("[data-otp-title]").textContent = TITLES[state.purpose] || "Enter the code";
    flow.querySelector("[data-otp-submit]").textContent = SUBMIT[state.purpose] || "Verify";
    resetFields.hidden = state.purpose !== "reset";
    flow.querySelectorAll("[data-login-only]").forEach(function (n) { n.hidden = state.purpose !== "login" || !state.hasPassword; });
    flow.querySelector('[data-step="otp"] [data-go="identify"]').hidden = state.purpose === "verify";
    show("otp");
    startTimer(cooldown);
  }

  function requestOtp(form, purpose, extra) {
    state.purpose = purpose;
    state.extra = extra || {};
    var payload = Object.assign({ email: state.email, purpose: purpose }, state.extra);
    if (form) setBusy(form, true, "Sending code...");
    return post(urls.request, payload).then(function (res) {
      if (form) setBusy(form, false);
      var d = res.data;
      if (res.ok && d.ok) { showOtp(d.masked, d.cooldown, d.length); return; }
      if (d.code === "cooldown") { showOtp(d.masked, d.retry_after); setAlert("A code was sent a moment ago. Please check your inbox."); return; }
      if (d.code === "no_account") { enterSignup(); setAlert(d.message); return; }
      if (d.code === "exists") { show("identify"); setAlert(d.message); return; }
      if (form) showErrors(form, d); else setAlert(d.message || "Something went wrong. Please try again.");
    }).catch(function () {
      if (form) setBusy(form, false);
      setAlert("Network problem. Please check your connection and try again.");
    });
  }

  function enterSignup() {
    flow.querySelector("[data-signup-email]").textContent = state.email;
    show("signup");
  }

  function submitOtp() {
    if (state.busy) return;
    var form = flow.querySelector('[data-form="otp"]');
    clearFieldErrors();
    if (code().length !== state.length) { setAlert("Please enter the full " + state.length + "-digit code."); boxesWrap.classList.add("error"); return; }
    var data = { email: state.email, purpose: state.purpose, code: code(), next: state.next };
    if (state.purpose === "reset") {
      data.new_password1 = form.querySelector('[name="new_password1"]').value;
      data.new_password2 = form.querySelector('[name="new_password2"]').value;
    }
    setBusy(form, true, "Verifying...");
    post(urls.verify, data).then(function (res) {
      setBusy(form, false);
      var d = res.data;
      if (res.ok && d.ok) { finish(d); return; }
      showErrors(form, d);
      if (d.code === "invalid" || d.code === "locked" || d.code === "expired") {
        boxesWrap.classList.add("error");
        if (!reduce) setTimeout(function () { boxesWrap.classList.remove("error"); }, 600);
        clearBoxes();
        if (d.code === "locked" || d.code === "expired") { clearInterval(state.timer); startTimer(0); }
      }
    }).catch(function () {
      setBusy(form, false);
      setAlert("Network problem. Please check your connection and try again.");
    });
  }

  function finish(d) {
    var titles = { plogin: "You are signed in", login: "You are signed in", signup: "Welcome aboard!", reset: "Password updated", verify: "Email verified" };
    var texts = { plogin: "Taking you back now...", login: "Taking you back now...", signup: "Your account is ready. Taking you back now...", reset: "You are signed in with your new password.", verify: "Thank you. Your email is confirmed." };
    flow.querySelector("[data-done-title]").textContent = titles[state.purpose] || "Done";
    flow.querySelector("[data-done-text]").textContent = texts[state.purpose] || "";
    show("done");
    setTimeout(function () { go(d.redirect); }, reduce ? 0 : 900);
  }

  // ------------------------------------------------------------- the forms
  flow.querySelector('[data-form="identify"]').addEventListener("submit", function (e) {
    e.preventDefault();
    var form = e.currentTarget;
    clearFieldErrors();
    var email = form.querySelector('[name="email"]').value.trim().toLowerCase();
    var digits = email.replace(/[\s+-]/g, "");
    var looksMobile = /^(91)?[6-9][0-9]{9}$/.test(digits);
    if (!looksMobile && !validEmail(email)) { fieldError(form.querySelector('[name="email"]'), "Please enter a valid email address or mobile number."); return; }
    state.email = email;
    setBusy(form, true, "Checking...");
    post(urls.identify, { email: email }).then(function (res) {
      setBusy(form, false);
      var d = res.data;
      if (!res.ok || !d.ok) { showErrors(form, d); return; }
      if (d.kind === "phone") {
        state.email = d.phone;
        state.hasPassword = false;
        if (!d.exists) { setAlert("No account is linked to this verified mobile number. Use your email address, then verify your number in Profile."); return; }
        if (!d.sms) { setAlert("Sign-in by mobile number is not available yet. Please use your email address."); return; }
        requestOtp(form, "plogin");
        return;
      }
      state.hasPassword = d.has_password;
      if (d.exists) {
        flow.querySelector("[data-password-email]").textContent = email;
        requestOtp(form, "login");
      } else {
        enterSignup();
      }
    }).catch(function () { setBusy(form, false); setAlert("Network problem. Please check your connection and try again."); });
  });

  flow.querySelector('[data-form="signup"]').addEventListener("submit", function (e) {
    e.preventDefault();
    var form = e.currentTarget;
    clearFieldErrors();
    var name = form.querySelector('[name="name"]').value.trim();
    var phone = form.querySelector('[name="phone"]').value.trim();
    var bad = false;
    if (name.length < 2) { fieldError(form.querySelector('[name="name"]'), "Please enter your full name."); bad = true; }
    var digits = phone.replace(/\D/g, "").replace(/^(91|0)(?=\d{10}$)/, "");
    if (!/^[6-9]\d{9}$/.test(digits)) { fieldError(form.querySelector('[name="phone"]'), "Enter a valid 10-digit mobile number."); bad = true; }
    if (bad) return;
    state.hasPassword = false;
    requestOtp(form, "signup", { name: name, phone: phone });
  });

  flow.querySelector('[data-form="otp"]').addEventListener("submit", function (e) { e.preventDefault(); submitOtp(); });

  flow.querySelector('[data-form="password"]').addEventListener("submit", function (e) {
    e.preventDefault();
    var form = e.currentTarget;
    clearFieldErrors();
    var password = form.querySelector('[name="password"]').value;
    if (!password) { fieldError(form.querySelector('[name="password"]'), "Please enter your password."); return; }
    setBusy(form, true, "Signing in...");
    var data = { username: state.email, password: password, next: state.next };
    if (form.querySelector('[name="remember"]').checked) data.remember = "on";
    post(urls.login, data).then(function (res) {
      setBusy(form, false);
      if (res.ok && res.data.ok) { state.purpose = "login"; finish(res.data); return; }
      showErrors(form, res.data);
    }).catch(function () { setBusy(form, false); setAlert("Network problem. Please check your connection and try again."); });
  });

  flow.querySelector('[data-form="reset"]').addEventListener("submit", function (e) {
    e.preventDefault();
    var form = e.currentTarget;
    clearFieldErrors();
    var email = form.querySelector('[name="email"]').value.trim().toLowerCase();
    if (!validEmail(email)) { fieldError(form.querySelector('[name="email"]'), "Please enter a valid email address."); return; }
    state.email = email;
    state.hasPassword = true;
    requestOtp(form, "reset");
  });

  // ------------------------------------------------------------ navigation
  flow.addEventListener("click", function (e) {
    var go_ = e.target.closest("[data-go]");
    if (go_) {
      e.preventDefault();
      var target = go_.dataset.go;
      if (target === "password") { flow.querySelector("[data-password-email]").textContent = state.email; }
      if (target === "identify") { clearInterval(state.timer); }
      show(target);
      return;
    }
    if (e.target.closest("[data-resend]")) { e.preventDefault(); requestOtp(null, state.purpose, state.extra); return; }
    if (e.target.closest("[data-forgot]")) { e.preventDefault(); requestOtp(null, "reset"); return; }
    if (e.target.closest("[data-send-login-otp]")) { e.preventDefault(); requestOtp(null, "login"); }
  });

  // ------------------------------------------------------ public entry points
  function resetAll() {
    flow.querySelectorAll("form").forEach(function (f) { f.reset(); });
    clearInterval(state.timer);
    state.email = ""; state.purpose = ""; state.extra = {};
    show("identify");
  }
  window.openAuth = function (mode, next) {
    state.next = next || (location.pathname + location.search);
    resetAll();
    if (modal) modal.show();
  };
  if (modalEl) {
    modalEl.addEventListener("shown.bs.modal", function () {
      var input = flow.querySelector('[data-step="identify"] input');
      if (input && !flow.querySelector('[data-step="identify"]').hidden) input.focus();
    });
  }

  // -------------------------------------------------------------- page start
  var start = flow.dataset.start || "identify";
  if (flow.dataset.email) {
    state.email = flow.dataset.email;
    flow.querySelector('[name="email"]').value = state.email;
    flow.querySelector("[data-password-email]").textContent = state.email;
  }
  if (start === "reset") {
    show("reset");
    var resetInput = flow.querySelector('[data-form="reset"] [name="email"]');
    if (state.email) resetInput.value = state.email;
  } else if (start === "verify") {
    state.hasPassword = false;
    if (flow.dataset.autosend) requestOtp(null, "verify"); else { state.purpose = "verify"; showOtp(state.email, 0); }
  } else {
    show("identify");
  }
})();
